from logging import getLogger
from itertools import cycle
from collections import OrderedDict
from contextlib import suppress
from typing import Optional, AsyncGenerator

from asyncio import (
    create_task,
    wait,
    get_running_loop,
    BaseEventLoop,
    CancelledError,
    Future,
    Task,
    Queue,
    TimerHandle,
    FIRST_COMPLETED,
)
from anyio import move_on_after

# from grpc.aio import Metadata
# from grpc.aio import EOF
from google.protobuf.message import Message as ProtobufMessage
from grpc._cython.cygrpc import _ConcurrentRpcLimiter

from chatp.proto.services.user.user_pb2 import UserKickedOff
from chatp.proto.services.friend.friend_pb2 import (
    FriendRequest,
    FriendConfirm,
)
from chatp.proto.services.transfer.msg_data_pb2 import ServerMsgData
from chatp.proto.services.push.push_pb2 import (
    PUSH_FRIEND_REQUEST,
    PUSH_FRIEND_CONFIRM,
    PUSH_USER_KICKED_OFF,
    PUSH_USER_MESSAGE,
    ACK_USER_MESSAGE,
    PUSH_SUCCESS,
    MessageLog,
    PubEventAckFromUser,
    PubEventToUser,
    PubEventToGateway,
    PubEventAckFromGateway,
    ConsumerFeedback,
)
from chatp.manager.grpc_client import GrpcClientManager
from chatp.message.queue import AckQueue

from manager.session import SessionManager
from manager.tasks import TaskManager
from rpc.push_service import PushService
from utils.model import SESSION_CLOSING

# Received PushMessage: OnlineMessage & FriendNotification & UserKickedOff
# Messages must be forwarded to WebsocketView


logger = getLogger("PushController")
logger.setLevel(10)
MAX_INT32 = 2 << 31


# mainly work:
# 1.manage batch confirmation
# 2.dispatch event to user's write queue
class PushChannel:
    def __init__(
        self,
        subscribe_key: bytes,
        push_stub: PushService,
        channel_number: int,
        *,
        grpc_manager: GrpcClientManager,
        ws_manager: SessionManager,
        task_manager: TaskManager,
        loop: BaseEventLoop,
    ):
        self.subscribe_key = subscribe_key
        self.push_stub = push_stub

        self.grpc_manager = grpc_manager
        self.ws_manager = ws_manager
        self.task_manager = task_manager

        self.channel_number = channel_number
        self.read_queue = Queue(maxsize=512)

        self.ack_queue = AckQueue()
        self.ack_waiter = Future()
        self.ack_trigger_handle: Optional[TimerHandle] = None

        self.stream_task: Task
        self.pending_writing_waiter = Future()
        self.cancel_writing_waiter = Future()
        self.done_writing_waiter = Future()
        self.consumers: OrderedDict[int, Task] = OrderedDict()

        self._loop = loop
        self._limiter = _ConcurrentRpcLimiter(512, loop=loop)

        self._handlers = {
            PUSH_FRIEND_REQUEST: self._friend_request_handler,
            PUSH_FRIEND_CONFIRM: self._friend_confirm_handler,
            PUSH_USER_KICKED_OFF: self._user_kicked_off_handler,
            PUSH_USER_MESSAGE: self._user_message_handler,
        }

    @property
    def sessions(self):
        return self.ws_manager._sessions

    def _friend_handler_helper(FriendMessage: ProtobufMessage, name: str):
        async def _inner_impl(self: "PushChannel", event: PubEventToGateway):
            logger.info(f"received one friend message: {name}")
            payload = FriendMessage.FromString(event.evt_data)
            start_id = SessionManager.DEVICE_KINDS_NUM * payload.link.address_id
            end_id = SessionManager.DEVICE_KINDS_NUM + start_id
            sessions_get = self.sessions.get
            targets = tuple(
                session
                for session_key in range(start_id, end_id)
                if (session := sessions_get(session_key)) is not None and session.active
            )
            delivery_id = event.delivery_id
            if targets:
                event = PubEventToUser(
                    log=MessageLog(
                        evt_tp=event.evt_tp,
                        channel_number=self.channel_number,
                        delivery_id=delivery_id,
                    ),
                    evt_data=event.evt_data,
                )
                task_factory = self._loop.create_task
                tasks = tuple(
                    task_factory(session.write_queue.put(event)) for session in targets
                )
                await wait(tasks)
            else:
                # TODO add retry & timeout
                self.ack_queue.add(delivery_id)

        _inner_impl.__name__ = name
        _inner_impl.__qualname__ = f"manager.push.PushChannel.{name}"
        return _inner_impl

    _friend_request_handler = _friend_handler_helper(
        FriendRequest, name="_friend_request_handler"
    )
    _friend_confirm_handler = _friend_handler_helper(
        FriendConfirm, name="_friend_confirm_handler"
    )

    async def _user_kicked_off_handler(self, event: PubEventToGateway):
        payload = UserKickedOff.FromString(event.evt_data)
        uid, device_tp = payload.uid, payload.device_tp
        session_key = uid * SessionManager.DEVICE_KINDS_NUM + device_tp
        if self.task_manager.cancel(session_key):  # execute clearing in next loop
            self.sessions[session_key].state = SESSION_CLOSING  # dont deactivate
            if await self.ws_manager.wait_for_recycle(session_key, timeout=5):
                self.ack_queue.add(event.delivery_id)
                self.ack_waiter.set_result(None)
            else:  # TODO check timeout, how to do?
                logger.warning("wait_for_recycle timeout!!!")
        else:  # old session already ends its life
            self.ack_queue.add(event.delivery_id)
            self.ack_waiter.set_result(None)

    # same with FriendHandler, later may add customized error handle
    async def _user_message_handler(self, event: PubEventToGateway):
        payload = ServerMsgData.FromString(event.evt_data)
        start_id = SessionManager.DEVICE_KINDS_NUM * payload.data.receiver_id
        end_id = SessionManager.DEVICE_KINDS_NUM + start_id
        sessions_get = self.sessions.get
        targets = tuple(
            session
            for session_key in range(start_id, end_id)
            if (session := sessions_get(session_key)) is not None and session.active
        )
        delivery_id = event.delivery_id
        if targets:
            event = PubEventToUser(
                log=MessageLog(
                    evt_tp=event.evt_tp,
                    channel_number=self.channel_number,
                    delivery_id=delivery_id,
                ),
                evt_data=event.evt_data,
            )
            task_factory = self._loop.create_task
            tasks = tuple(
                task_factory(session.write_queue.put(event)) for session in targets
            )
            await wait(tasks)
        else:
            # TODO add retry & timeout
            self.ack_queue.add(delivery_id)

    async def consumer_feedback(self) -> AsyncGenerator[ConsumerFeedback, None]:
        ack_queue = self.ack_queue
        cancel_waiter = self.cancel_writing_waiter
        done_waiter = self.done_writing_waiter
        pair = [self.ack_waiter, cancel_waiter]
        while True:
            await wait(pair, return_when=FIRST_COMPLETED)
            for r in ack_queue.iterator():
                yield ConsumerFeedback(
                    status=PUSH_SUCCESS,
                    confirm=PubEventAckFromGateway(start_id=r.start, end_id=r.end),
                )

            ack_queue.clear()
            self.ack_trigger_handle = None

            if not cancel_waiter.done():
                self.ack_waiter = pair[0] = Future()
            else:
                if not done_waiter.done():
                    done_waiter.set_result(None)
                break

    async def stream_handler(self):
        request_iterator = self.consumer_feedback()
        subscribe_stream = self.push_stub.SubscribeStream(
            request_iterator,
            metadata=(("gateway_addr", self.subscribe_key),),
            wait_for_ready=True,  # important, when push service onlines
        )
        initial_metadata = await subscribe_stream.initial_metadata()
        self.instance_id = instance_id = initial_metadata["instance_id"]
        logger.info(f"Stream Handler was attached to a new channel [{instance_id}]")

        consumers = self.consumers
        limiter, handlers = self._limiter, self._handlers
        # subscribe_stream = cast(
        #     AsyncGenerator[PubEventToGateway, None], subscribe_stream
        # )
        ws_manager = self.ws_manager
        async for event in subscribe_stream:
            if ws_manager.shutdown:
                subscribe_stream.cancel()  # shield
                break

            delivery_id = event.delivery_id
            await limiter.check_before_request_call()
            task = create_task(handlers[event.evt_tp](event))  # push to user
            task.add_done_callback(lambda _: consumers.pop(delivery_id, None))
            task.add_done_callback(limiter.decrease_once_finished)
            consumers[delivery_id] = task

        # subscribe_stream.done_writing()  # called after request_iterator exhausted
        logger.info(f"Stream Handler exited successfully [{instance_id}]")

    async def connect(self):
        self.stream_task = stream_task = self._loop.create_task(self.stream_handler())
        pending_writing_waiter = self.pending_writing_waiter
        await wait([pending_writing_waiter, stream_task], return_when=FIRST_COMPLETED)

        if not pending_writing_waiter.done():
            pending_writing_waiter.set_result(None)
        elif pending_writing_waiter.cancelled():
            logger.warning("PushStream service_consumer was cancelled")

        if not (waiter := self.cancel_writing_waiter).done():
            waiter.set_result(None)  # safely clear request_iterator

        # if there are still some pending tasks, cancel them
        # be captured PushService, maybe timeout or return failed directly
        to_cancel = []
        for task in self.consumers.values():
            if not task.done():
                task.cancel()
                to_cancel.append(task)
        if to_cancel:
            await wait(to_cancel)

        # Inflight: notify the peer that `request_iterator` is exhausted.
        # then expect the peer ends its coroutine
        with move_on_after(5) as scope:  # in case consumer feedback failed
            await self.done_writing_waiter

        if scope.cancel_called:
            logger.warning("PushStream took too much time to clear request_iterator")

        if stream_task.done():
            logger.info("PushStream exited 0")
        else:
            with move_on_after(5) as scope:  # in case, network issue
                await stream_task

            if scope.cancel_called:
                logger.warning("PushStream took too much time to cancel stream_task")


class PushManager:
    def __init__(
        self,
        grpc_manager: GrpcClientManager,
        ws_manager: SessionManager,
        task_manager: TaskManager,
        subscribe_key: str,
        *,
        loop: Optional[BaseEventLoop] = None,
    ):
        self.grpc_manager = grpc_manager
        self.ws_manager = ws_manager
        self.task_manager = task_manager

        self.subscribe_key = bytes(subscribe_key, "ascii")

        if loop is None:
            loop = get_running_loop()
        self._loop = loop

        self.channel_number_generator = cycle(range(MAX_INT32))
        self.channels: dict[int, PushChannel] = {}

        self.ack_delay = 0.02  # 20ms

        self.reader_task: Task
        self.channel_queue: Queue[
            ProtobufMessage
        ] = Queue()  # read from user, write to PushChannel
        # self.message_queue: Queue[
        #     GrpcMessageWrapper
        # ] = Queue()  # read from MQStream, write to user

    async def __aenter__(self):
        self.rpc_task = create_task(self.ack_to_rpc())
        # self.user_task = create_task(self.ack_to_user())
        return self

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        if not (rpc_task := self.rpc_task).done():
            rpc_task.cancel()
            with suppress(CancelledError):
                await rpc_task

        # if not (user_task := self.user_task).done():
        #     user_task.cancel()
        # await wait([rpc_task, user_task])

    async def ack_to_user(self):
        queue_get = self.message_queue.get
        ws_manager = self.ws_manager
        # create_task = self._loop.create_task
        while not ws_manager.shutdown:  # shutdown means all conns are already closed
            data = await queue_get()
            session_key = data.session_key
            if (session := ws_manager.get(session_key)) is not None:
                logger.info(
                    "user message has been published successfully, needs to ack"
                )
                session.write_queue.put_nowait(
                    PubEventToUser(
                        log=MessageLog(
                            evt_tp=ACK_USER_MESSAGE,
                            channel_number=0,
                            delivery_id=data.msg_data_wrapper.delivery_id,
                        ),
                    )
                )  # AckEvent

    async def ack_to_rpc(self):
        def ack_cb(channel: PushChannel):
            if not (waiter := channel.ack_waiter).done():
                waiter.set_result(None)

        queue_get = self.channel_queue.get
        channels = self.channels

        ack_delay = self.ack_delay
        loop_call_later = self._loop.call_later
        while True:
            event: PubEventAckFromUser = await queue_get()
            for log in event.logs:
                channel = channels[log.channel_number]
                channel.ack_queue.add(log.delivery_id)
                if channel.ack_trigger_handle is None:
                    # wait 20ms default, expects more ack
                    channel.ack_trigger_handle = loop_call_later(
                        ack_delay, ack_cb, channel
                    )

    async def connect_push_channel(self, push_addr: str, push_stub: PushService):
        logger.info("Begin to subscribe stream supplied by PushService: %s", push_addr)

        channel_number = next(self.channel_number_generator)
        self.channels[channel_number] = channel = PushChannel(
            self.subscribe_key,
            push_stub,
            channel_number,
            grpc_manager=self.grpc_manager,
            ws_manager=self.ws_manager,
            task_manager=self.task_manager,
            loop=self._loop,
        )
        try:
            await channel.connect()
        except Exception as exc:
            logger.error(
                f"Found exception in push channel[{push_addr}]: %s", exc, exc_info=exc
            )
        finally:
            del self.channels[channel_number]
