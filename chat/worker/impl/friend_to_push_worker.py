from types import FrameType
from typing import Optional, Callable, Union
from time import monotonic
from functools import partial
from contextlib import AsyncExitStack

from asyncio import (
    CancelledError,
    Future,
    Queue,
    QueueEmpty,
    wait,
    current_task,
    get_running_loop,
)
from anyio import create_task_group
from aio_pika import IncomingMessage
from google.protobuf.message import Message as ProtobufMessage

from chatp.proto.services.friend.friend_pb2 import (
    FriendEvent,
    FriendRequest,
    FriendConfirm,
    FRIEND_REQUEST,
    FRIEND_CONFIRM,
)
from chatp.proto.services.push.push_pb2 import (
    PubEventType,
    PUSH_FRIEND_REQUEST,
    PUSH_FRIEND_CONFIRM,
)
from chatp.rmq.pika.consumer import RMQConsumer
from chatp.rmq.pika.backend import RMQBackend
from chatp.rmq.pika.model import ConsumerMessage
from chatp.redis.model import REDIS_SUCCESS
from chatp.redis.client import RedisClient
from chatp.manager.grpc_client import GrpcClientManager
from chatp.utils.signals import install_signal_handlers

from .base_worker import RMQWorker
from rpc.push_service import PushService


class FriendWorker(RMQWorker):
    backend: RMQBackend

    def __init__(
        self,
        setting: dict,
        grpc_manager: GrpcClientManager,
        redis_client: RedisClient,
    ):
        super().__init__(setting)
        self.grpc_manager = grpc_manager
        self.redis_client = redis_client

        self.push_service_getter: Callable[[str], PushService] = partial(
            grpc_manager.find_service, "PushService"
        )

    async def initialize(self):  # create consumer topo
        setting = self.setting
        consumer_factory = self.backend.create_consumer(
            queue_name=setting["FRIEND_QUEUE_NAME_TO_PUSH"],
            exchange_type=setting["FRIEND_EXCHANGE_TYPE"],
            exchange_name=setting["FRIEND_EXCHANGE_NAME"],
        )

        self.loop = loop = get_running_loop()
        create_task = loop.create_task
        tasks = [create_task(consumer_factory(initial_qos=1024))]
        await wait(tasks)
        self.consumers = [task.result() for task in tasks]
        self.logger.info("RMQ Service connected.")

    async def handler(self, consumer: RMQConsumer):
        def on_consume(pika_message: IncomingMessage) -> None:
            message = ConsumerMessage(pika_message)
            if not self.validate_source(pika_message):
                self.loop.create_task(self.discard_message(message))
                return

            entity = pika_message.body
            event: FriendEvent = FriendEvent.FromString(entity)
            if (evt_tp := event.evt_tp) is FRIEND_REQUEST:
                request_queue_putter((event.request, message))
            elif evt_tp is FRIEND_CONFIRM:
                confirm_queue_putter((event.confirm, message))
            else:
                pass
            self.total_count += 1

        def on_completed() -> Optional[ConsumerMessage]:
            if request_event_queue:
                try:
                    while request_message := request_event_queue.get_nowait():
                        continue
                except QueueEmpty:
                    request_message: IncomingMessage = request_message[1]._message
            else:
                request_message = None

            if confirm_event_queue:
                try:
                    while confirm_message := confirm_event_queue.get_nowait():
                        continue
                except QueueEmpty:
                    confirm_message: IncomingMessage = confirm_message[1]._message
            else:
                confirm_message = None

            if request_message and confirm_message:
                return (
                    request_message
                    if request_message.delivery_tag > confirm_message.delivery_tag
                    else confirm_message
                )
            else:
                return request_message or confirm_message

        request_event_queue = Queue(maxsize=512)
        request_queue_putter = request_event_queue.put_nowait

        confirm_event_queue = Queue(maxsize=512)
        confirm_queue_putter = confirm_event_queue.put_nowait

        async with consumer.start_listen(on_consume, on_completed):
            async with create_task_group() as tg:
                tg.start_soon(
                    self.friend_handler, request_event_queue, PUSH_FRIEND_REQUEST
                )
                tg.start_soon(
                    self.friend_handler, confirm_event_queue, PUSH_FRIEND_CONFIRM
                )

    async def friend_handler(
        self,
        queue: Queue[tuple[ProtobufMessage, ConsumerMessage]],
        pub_event_type: PubEventType,
    ):
        async def _handler(
            data: Union[FriendRequest, FriendConfirm],
            message: ConsumerMessage,
        ):
            address_id = data.link.address_id
            if exists := await self.user_online_check(address_id):
                if await self.push_to_gateway(
                    pub_event_type, address_id, data, hash_key=str(address_id)
                ):
                    if await message.ack():
                        self.succeed_count += 1
                    else:
                        logger.exception(
                            "Found connection lost when ack.", exc_info=False
                        )
                else:
                    if await message.reject(requeue=True):
                        self.failed_count += 1
                    else:
                        logger.exception(
                            "Found connection lost when reject.", exc_info=False
                        )
            elif exists is None:  # RedisTimeout or RedisFailed
                logger.exception("Found timeout when calling RedisClient<redis_hlen>.")
                if await message.reject(requeue=True):
                    self.failed_count += 1
                else:
                    logger.exception(
                        "Found connection lost when reject.", exc_info=False
                    )

            else:  # offline, do nothing
                if not await message.ack():
                    logger.exception("Found connection lost when ack.", exc_info=False)

        logger = self.logger
        queue_getter = queue.get
        create_task = self.loop.create_task
        tasks = set()
        try:
            while True:
                data, message = await queue_getter()
                task = create_task(_handler(data, message))
                task.add_done_callback(tasks.discard)
                tasks.add(task)
        except CancelledError:
            if tasks:
                await wait(tasks)
                tasks.clear()
            return

    async def user_online_check(self, uid: int):
        data, status = await self.redis_client.redis_hlen(
            f"chatp:user:gateway_addr:uid:{uid}", timeout=3
        )
        return data > 0 if status is REDIS_SUCCESS else None

    async def push_to_gateway(
        self,
        data_type: PubEventType,
        address_id: int,
        message: Union[FriendRequest, FriendConfirm],
        *,
        hash_key: str,
    ) -> bool:
        service: Optional[PushService] = self.push_service_getter(hash_key=hash_key)
        if service is None:
            self.logger.warning(
                "PushService is unavailable temporarily, message is lost"
            )
            return False

        return await service.push_data(
            data_type=data_type,
            address_id=address_id,
            payload=message.SerializeToString(),
            timeout=8,
        )


async def serve(_, grpc_manager: GrpcClientManager, app_setting: Optional[dict]):
    from uvicorn import Config

    config = Config(app=None, log_level=10)
    del config

    get_running_loop().set_debug(True)

    waiter = Future()
    curr_task = current_task()
    first_signal_time: Optional[float] = None

    def handle_exit(sig: int, frame: Optional[FrameType]):
        print("> Catched a SIGINT signal from os kernel")
        nonlocal waiter, first_signal_time
        if first_signal_time is None:
            first_signal_time = monotonic()
            if not waiter.done():
                waiter.set_result(None)
        elif monotonic() > first_signal_time + 15:
            print("Force to exit...")
            curr_task.cancel()

    redis_client = RedisClient()
    worker = FriendWorker(app_setting, grpc_manager, redis_client)
    async with AsyncExitStack() as exitstack:
        await exitstack.enter_async_context(redis_client)
        await exitstack.enter_async_context(grpc_manager)
        await exitstack.enter_async_context(worker)
        install_signal_handlers(handle_exit)
        await waiter
        print("Begin to exit...")
