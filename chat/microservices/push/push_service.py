from logging import getLogger
from datetime import datetime
from typing import Optional, AsyncGenerator, AsyncIterable

from asyncio import (
    TimeoutError,
    BaseEventLoop,
    get_running_loop,
    wait_for,
    wait,
)

import grpc
from anyio import create_task_group
from aio_pika.message import IncomingMessage

from utils.model import DIED
from utils.collector import EventCollector, EventChannel

from chatp.redis.client import RedisClient
from chatp.redis.model import *
from chatp.utils.uuid import generate
from chatp.proto.services.push.push_pb2_grpc import PushServicer as ProtoPushServicer
from chatp.proto.services.push.push_pb2 import (
    PubStatus,
    PUSH_SUCCESS,
    PUSH_TIMEOUT,
    PUSH_FAILED,
    PUSH_OFFLINE,
    PUSH_FRIEND_REQUEST,
    PUSH_FRIEND_CONFIRM,
    PUSH_FRIEND_SESSION,
    PUSH_USER_KICKED_OFF,
    PUSH_USER_MESSAGE,
    PubEventType,
    PubNotification,
    PubNotificationAck,
    PubNotificationHeader,
    PubEventToGateway,
    PubUserMessage,
    ConsumerFeedback,
    ControlMessageData,
    ControlMessageAck,
)
from chatp.proto.services.user.user_pb2 import UserDeviceType, UserKickedOff


datetime_utcnow = datetime.utcnow
logger = getLogger("PushService")


def get_timestamp():
    return int(datetime_utcnow().timestamp() * 1000)  # ms


class VirtualContext:
    __slots__ = "time_remaining"

    def __init__(self, constant_time: int | float = 10):
        self.time_remaining = lambda: constant_time


global_virtual_context = VirtualContext()


class PushServicer(ProtoPushServicer):
    def __init__(
        self,
        redis_client: RedisClient,
        loop: Optional[BaseEventLoop] = None,
    ):
        if loop is None:
            loop = get_running_loop()
        self._loop = loop

        self.instance_id = generate(5)

        self.redis_client = redis_client
        self.collector = EventCollector()

        self._handlers = {
            PUSH_FRIEND_REQUEST: self._friend_request_handler,
            PUSH_FRIEND_CONFIRM: self._friend_confirm_handler,
            PUSH_FRIEND_SESSION: self._friend_session_handler,
            PUSH_USER_MESSAGE: self._user_message_handler,
            PUSH_USER_KICKED_OFF: self._user_kicked_off_handler,
        }

    def _handler_helper(evt_tp: PubEventType, name: str):
        async def _inner_impl(
            self: "PushServicer",
            header: PubNotificationHeader,
            payload: bytes,
            context: grpc.aio.ServicerContext,
        ):
            results, status = await self.redis_client.redis_hgetall(
                key=f"chatp:user:gateway_addr:uid:{header.address_id}",
                timeout=5,
            )
            if status is REDIS_SUCCESS:
                if results:
                    event = PubEventToGateway(evt_tp=evt_tp, evt_data=payload)
                    collector = self.collector
                    if len(addrs := tuple(set(results.values()))) == 1:
                        waiter = await collector.send(event, addrs[0])
                        try:
                            await wait_for(waiter, timeout=context.time_remaining())
                        except TimeoutError:  # still dont received ConsumerFeedback
                            logger.exception(
                                f"Found timeout when waiting resp on {PubEventType.Name(evt_tp)}. [{context.time_remaining()}]"
                            )
                            status = PUSH_TIMEOUT
                        else:
                            logger.info(
                                f"Successfully pushed one {PubEventType.Name(evt_tp)} [{context.time_remaining()}]"
                            )
                            status = waiter.result()
                    else:
                        waiters = await collector.send_mulitple(event, *addrs)
                        done, pending = await wait(
                            waiters, timeout=context.time_remaining()
                        )
                        if pending:
                            status = PUSH_TIMEOUT
                            for waiter in pending:
                                waiter.set_result(PUSH_TIMEOUT)
                        else:
                            status = (
                                PUSH_SUCCESS
                                if all(
                                    waiter.result() is PUSH_SUCCESS for waiter in done
                                )
                                else PUSH_FAILED
                            )
                    return status
                else:  # currently, user becomes offline
                    logger.info(
                        f"User was already offline on {PubEventType.Name(evt_tp)} [{context.time_remaining()}]"
                    )
                    return PUSH_OFFLINE
            elif status is REDIS_TIMEOUT:
                logger.exception(
                    f"Found timeout when waiting the redis query on {PubEventType.Name(evt_tp)} [{context.time_remaining()}]"
                )
                return PUSH_TIMEOUT
            else:
                logger.error(
                    f"Failed to query redis on {PubEventType.Name(evt_tp)} [{context.time_remaining()}]"
                )
                return PUSH_FAILED

        _inner_impl.__name__ = name
        _inner_impl.__qualname__ = f"push_service.PushServicer.{name}"
        return _inner_impl

    _friend_request_handler = _handler_helper(
        PUSH_FRIEND_REQUEST, "_friend_request_handler"
    )
    _friend_confirm_handler = _handler_helper(
        PUSH_FRIEND_CONFIRM, "_friend_confirm_handler"
    )
    _friend_session_handler = _handler_helper(
        PUSH_FRIEND_SESSION, "_friend_session_handler"
    )

    _user_message_handler = _handler_helper(PUSH_USER_MESSAGE, "_user_message_handler")

    async def _user_kicked_off_handler(
        self,
        header: PubNotificationHeader,
        payload: bytes,
        context: grpc.aio.ServicerContext,
    ) -> PubStatus:
        address_id, device_tp = header.address_id, int.from_bytes(payload)
        addr, status = await self.redis_client.redis_hget(
            key=f"chatp:user:gateway_addr:uid:{address_id}",
            field=UserDeviceType.Name(device_tp),
            timeout=context.time_remaining(),
        )
        if status is REDIS_SUCCESS:
            if addr:
                waiter = await self.collector.send(
                    PubEventToGateway(
                        evt_tp=PUSH_USER_KICKED_OFF,
                        evt_data=UserKickedOff(
                            uid=address_id,
                            device_tp=device_tp,
                            timestamp=get_timestamp(),
                        ).SerializeToString(),
                    ),
                    addr,
                )
                try:
                    await wait_for(waiter, timeout=context.time_remaining())
                except TimeoutError:  # still dont received ConsumerFeedback
                    logger.exception(
                        f"wait push resp timeout. [{context.time_remaining()}]"
                    )
                    status = PUSH_TIMEOUT
                else:
                    logger.info(
                        f"successfully pushed user kicked off [{context.time_remaining()}]"
                    )
                    status = waiter.result()
                return status
            else:
                logger.info(
                    f"user was already offline when kicked off [{context.time_remaining()}]"
                )
                return PUSH_OFFLINE
        elif status is REDIS_TIMEOUT:
            logger.exception(f"wait redis query timeout. [{context.time_remaining()}]")
            return PUSH_TIMEOUT
        else:
            logger.error(f"wait redis query failed. [{context.time_remaining()}]")
            return PUSH_FAILED

    async def PublishNotification(
        self, request: PubNotification, context: grpc.aio.ServicerContext
    ) -> PubNotificationAck:
        header = request.header
        status = await self._handlers[header.data_type](
            header, request.payload, context
        )
        return PubNotificationAck(status=status)

    async def SubscribeStream(
        self,
        request_iterator: AsyncIterable[ConsumerFeedback],
        context: grpc.aio.ServicerContext,
    ) -> AsyncGenerator[PubEventToGateway, None]:
        print("subscribe stream")
        metadata = context.invocation_metadata()  # tuple
        # metadata: <(_Metadatum, len()=2), _Metadatum(key, value)>
        gateway_addr = bytes(metadata[1].value, "ascii")
        collector = self.collector
        channel = collector.register(gateway_addr)

        async def consumer_feedback(
            request_iterator: AsyncIterable[ConsumerFeedback],
            channel: EventChannel,
        ):
            async for feedback in request_iterator:
                channel.on_delivery(feedback)

            tg.cancel_scope.cancel()
            channel.state = DIED  # TODO needs to clear channel

        logger.info(f"gateway_addr: {gateway_addr} already entered.")
        await context.send_initial_metadata((("instance_id", self.instance_id),))
        async with create_task_group() as tg:
            tg.start_soon(consumer_feedback, request_iterator, channel)
            async for event, waiter in collector.dispatch(gateway_addr):
                if not waiter.done():
                    yield event

        logger.info(f"gateway_addr: {gateway_addr} already leaved.")

    async def ControlMessage(
        self, request: ControlMessageData, context: grpc.aio.ServicerContext
    ) -> ControlMessageAck:
        return super().ControlMessage(request, context)

    async def consume_event(self, message: IncomingMessage):
        event = PubUserMessage.FromString(message.body)
        status = await self._user_message_handler(
            PubNotificationHeader(
                data_type=PUSH_USER_MESSAGE, address_id=event.address_id
            ),
            event.payload,
            global_virtual_context,
        )
        if status in (PUSH_SUCCESS, PUSH_OFFLINE):
            await message.ack()
        else:
            await message.reject(requeue=True)
