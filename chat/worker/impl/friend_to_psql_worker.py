from types import FrameType
from typing import Optional, Callable, Coroutine, Union
from time import monotonic
from functools import partial
from contextlib import AsyncExitStack

from asyncio import (
    CancelledError,
    Future,
    Queue,
    QueueEmpty,
    wait,
    sleep,
    current_task,
    get_running_loop,
)
from anyio import create_task_group
from aio_pika import IncomingMessage

from chatp.proto.services.friend.friend_pb2 import (
    FRIEND_SUCCESS,
    FRIEND_TIMEOUT,
    FRIEND_FAILED,
    FriendRequest,
    FriendConfirm,
    FriendEvent,
    FRIEND_REQUEST,
    FRIEND_CONFIRM,
)
from chatp.rmq.pika.backend import RMQBackend
from chatp.rmq.pika.consumer import RMQConsumer
from chatp.rmq.pika.model import ConsumerMessage
from chatp.manager.grpc_client import GrpcClientManager
from chatp.utils.signals import install_signal_handlers
from chatp.rpc.model import GRPC_SUCCESS, GRPC_TIMEOUT, CallResult, GrpcStatus

from .base_worker import RMQWorker
from rpc.user_service import UserService


class FriendWorker(RMQWorker):
    backend: RMQBackend

    def __init__(
        self,
        setting: dict,
        grpc_manager: GrpcClientManager,
    ):
        super().__init__(setting)

        self.user_service_getter: Callable[[], UserService] = partial(
            grpc_manager.find_service, "UserService"
        )

    async def initialize(self):
        setting = self.setting
        consumer_factory = self.backend.create_consumer(
            queue_name=setting["FRIEND_QUEUE_NAME_TO_POSTGRES"],
            exchange_name=setting["FRIEND_EXCHANGE_NAME"],
            exchange_type=setting["FRIEND_EXCHANGE_TYPE"],
        )
        self.loop = loop = get_running_loop()
        create_task = loop.create_task
        tasks = [create_task(consumer_factory(initial_qos=128))]
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

        def on_completed() -> Optional[IncomingMessage]:
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

        request_event_queue, confirm_event_queue = Queue(maxsize=64), Queue(maxsize=64)
        request_queue_putter = request_event_queue.put_nowait
        confirm_queue_putter = confirm_event_queue.put_nowait
        async with consumer.start_listen(on_consume, on_completed):
            async with create_task_group() as tg:
                tg.start_soon(self.friend_handler, request_event_queue, self.add_friend)
                tg.start_soon(
                    self.friend_handler, confirm_event_queue, self.confirm_friend
                )
                # When process is shutdown, s.t. Ctrl-C, then TaskGroup is cancelled:
                # 1.cancel friend_handler -> dont create new task internally
                # 2.wait friend_handler to complete
                # PS: friend_handler handles CancelledError and waits all inflight tasks done

            # The outer `async with` block will cancel consumer & schedule on_completed
            # TODO the semantic of consumer.cancel, on_completed is unnecessary?

    async def friend_handler(
        self,
        queue: Queue[tuple[Union[FriendRequest, FriendConfirm], ConsumerMessage]],
        action: Callable[
            [Union[FriendRequest, FriendConfirm]],
            Coroutine[None, None, Optional[GrpcStatus]],
        ],
    ):
        async def _handler(
            request: Union[FriendRequest, FriendConfirm],
            message: ConsumerMessage,
        ):
            status = await action(request)
            if status is FRIEND_SUCCESS:
                self.logger.info(f"Called `{action.__name__}` successfully.")
                if await message.ack():
                    self.succeed_count += 1
                else:
                    self.logger.exception(
                        "Found connection lost when ack.",
                        exc_info=False,
                    )

            elif status is FRIEND_TIMEOUT:
                # Handling Timeout in SQL Server or Acquire Conn Timeout in SQL Client
                self.logger.exception(f"Found timeout in `{action.__name__}`.")
                if await message.reject(requeue=True):
                    self.failed_count += 1
                else:
                    self.logger.exception(
                        "Found connection lost when reject.",
                        exc_info=False,
                    )

            elif status is FRIEND_FAILED:  # Network issue in SQL Client
                self.logger.error(
                    f"Found unknown error in `{action.__name__}`.",
                    exc_info=False,
                )
                if await message.reject(requeue=True):
                    self.failed_count += 1
                else:
                    self.logger.exception(
                        "Found connection lost when reject.",
                        exc_info=False,
                    )

            else:  # Timeout or Failed
                if await message.reject(requeue=True):
                    self.failed_count += 1
                else:
                    self.logger.exception(
                        "Found connection lost when reject.",
                        exc_info=False,
                    )

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

    async def add_friend(self, request: FriendRequest) -> Optional[GrpcStatus]:
        service = self.user_service_getter()
        if service is None:
            await sleep(2)
            return
        result: CallResult = await service.AddFriend(request, timeout=5)
        if (grpc_status := result.status) is GRPC_SUCCESS:
            return result.data.status
        elif grpc_status is GRPC_TIMEOUT:
            self.logger.exception(
                "Found timeout when calling GrpcCall<FriendService.AddFriend>.",
                exc_info=False,
            )
            return
        else:
            self.logger.error(
                "Found unknown error when calling GrpcCall<FriendService.AddFriend>: ",
                result.info,
                exc_info=False,
            )
            return

    async def confirm_friend(self, confirm: FriendConfirm) -> Optional[GrpcStatus]:
        service = self.user_service_getter()
        if service is None:
            await sleep(2)
            return

        result: CallResult = await service.ConfirmFriend(confirm, timeout=10)
        if (grpc_status := result.status) is GRPC_SUCCESS:
            return result.data.status
        elif grpc_status is GRPC_TIMEOUT:
            self.logger.exception(
                "Found timeout when calling GrpcCall<FriendService.ConfirmFriend>.",
                exc_info=False,
            )
            return
        else:
            self.logger.error(
                "Found unknown error when calling GrpcCall<FriendService.ConfirmFriend>: ",
                result.info,
                exc_info=False,
            )
            return


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

    worker = FriendWorker(app_setting, grpc_manager)
    async with AsyncExitStack() as exitstack:
        await exitstack.enter_async_context(grpc_manager)
        await exitstack.enter_async_context(worker)
        install_signal_handlers(handle_exit)
        await waiter
