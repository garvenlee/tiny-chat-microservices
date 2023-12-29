from types import FrameType
from typing import Optional, Callable, Coroutine
from time import monotonic
from functools import partial
from collections import defaultdict
from contextlib import AsyncExitStack

from asyncio import Future, Task, Event, get_running_loop, current_task
from grpc._cython.cygrpc import _ConcurrentRpcLimiter

from chatp.multiprocess.worker import WorkerProcess
from chatp.manager.grpc_client import GrpcClientManager
from chatp.rmq.stream.backend import RMQStreamBackend
from chatp.rmq.stream.consumer import RMQStreamConsumer
from chatp.rmq.stream.model import StreamMessage
from chatp.redis.client import RedisClient
from chatp.utils.signals import install_signal_handlers
from chatp.proto.services.transfer.msg_data_pb2 import (
    RStreamMsgData,
    DLQ_ALL,
    DLQ_SESSION_ONLY,
    DLQ_INBOX_ONLY,
)
from chatp.proto.services.transfer.cass_storage_pb2 import CassMsgRequest

from .base_worker import RMQWorker, RabbitQueueType
from rmq.service import RMQPusher
from rpc.cass_storage_service import CassMessageService
from utils.pacer import MessagePacer, FilterState
from utils.mixin import PushMixin


class OutboxWorker(RMQWorker, PushMixin):
    backend: RMQStreamBackend

    def __init__(
        self,
        setting: dict,
        grpc_manager: GrpcClientManager,
        redis_client: RedisClient,
        rmq_pusher: RMQPusher,
    ):
        super().__init__(setting, queue_type=RabbitQueueType.STREAM_QUEUE)
        super(RMQWorker, self).__init__(
            grpc_manager,
            redis_client,
            rmq_pusher,
            broker_id=setting["APPID"],
        )

        self.pacer = MessagePacer(redis_client)
        self.cass_message_service_getter: Callable[
            [str], Optional[CassMessageService]
        ] = partial(grpc_manager.find_service, "CassMessageService")

        self.shutdown = False
        self.shutdown_event = Event()

    def close(self):
        self.shutdown_event.set()

    async def run(self):
        try:
            await self.shutdown_event.wait()
        finally:
            self.shutdown = True  # shield new tasks during shutdown routine
            # TODO unsubscribe first?
            # after unsubscribe, then store_offset will get failed?
            # similar, after cancel consumer, then nack will get failed?

            task_manager = self.task_manager
            await task_manager.wait_for_termination()
            # await task_manager.close()

            # then backend can be closed safely

    async def initialize(self):
        setting = self.setting
        super_stream_consumer: RMQStreamConsumer = await self.backend.create_consumer(
            super_stream=setting["RMQ_STREAM_NAME"],
            broker_name=setting["PLATFORM_ID"],
        )
        logger = self.logger
        logger.info("RMQ Service connected.")

        properties = defaultdict(str)
        properties.update(
            {
                "single-active-consumer": "true",
                "name": setting["CONSUMER_GROUP_NAME"],
                "super-stream": setting["RMQ_STREAM_NAME"],
            }
        )

        await super_stream_consumer.subscribe(
            callback=partial(
                self.on_message_wrapper,
                limiter=_ConcurrentRpcLimiter(1024, loop=get_running_loop()),
                task_factory=self.task_factory,
            ),
            decoder=RStreamMsgData.FromString,
            properties=properties,
        )
        self.consumer = super_stream_consumer
        logger.info("Subscribe message-stream successfully")

    async def on_message_wrapper(
        self,
        message: StreamMessage,
        *,
        limiter: _ConcurrentRpcLimiter,
        task_factory: Callable[[Coroutine], Task],
    ):
        # TODO Check Later after rstream adds its flow control
        # dont check message.frozen here, subsribe_cb_wrapper already did it
        if self.shutdown:  # shield new task
            # TODO but there are also new incoming messages from underlaying transport
            # await self.shutdown_event.wait()  # block the delivery_task
            return

        self.logger.info(
            f"received one message from {message.stream}: {message.offset}"
        )
        await limiter.check_before_request_call()
        if not self.shutdown and not message.frozen:  # ReCheck: fast exit
            task = task_factory(self.on_message(message))
            task.add_done_callback(limiter.decrease_once_finished)

    async def on_message(self, stream_message: StreamMessage):
        if stream_message.frozen:  # safe check
            return

        message: RStreamMsgData = stream_message.body
        msg_data = message.data
        sender_id, hash_key = msg_data.sender_id, str(msg_data.session_id)
        delivery_id, msg_id = message.delivery_id, message.message_id

        pacer = self.pacer
        status = await pacer.filter_or_not(sender_id, delivery_id, msg_id)
        match status:
            case FilterState.NEW_ITEM:
                # If consumption replay occurs due to the asynchronous offset-store,
                # there will be duplicate messages to write to cassandra, but cassandra
                # can automatically ignore it, and return it as handled successfully.
                # Now, needs to make concurrent network IO, and trace its result
                inflight_task = self.task_factory(
                    self.write_to_session(
                        CassMsgRequest(
                            message_data=msg_data,
                            delivery_id=delivery_id,
                            message_id=msg_id,
                        ),
                        hash_key=hash_key,
                        timeout=12,
                    )
                )
                # Priority Notification to read model, faster but introduce eventual consistency
                if not await self.notify_read_model(
                    msg_data, msg_id, delivery_id, hash_key=hash_key, timeout=8
                ):
                    await self.push_to_dlq(
                        message, DLQ_INBOX_ONLY, hash_key=hash_key, timeout=5
                    )

                # Assume that MQ Delivery will not fail
                if not await inflight_task:
                    await self.push_to_dlq(
                        message, DLQ_SESSION_ONLY, hash_key=hash_key, timeout=5
                    )

                stream_message.ack()  # eventual consistency
                await pacer.on_handled_new_item(sender_id, delivery_id, msg_id)

            case FilterState.CAN_IGNORE:
                stream_message.ack()
                return

            case FilterState.RETRY_REQUIRED:
                await self.push_to_dlq(message, DLQ_ALL, hash_key=hash_key, timeout=5)

                stream_message.ack()
                await pacer.on_handled_new_item(sender_id, delivery_id, msg_id)
                return

    async def write_to_session(
        self,
        cass_msg: CassMsgRequest,
        *,
        hash_key: str,
        timeout: int | float,
    ):
        service: Optional[CassMessageService] = self.cass_message_service_getter(
            hash_key=hash_key
        )
        if service is None:
            self.logger.warning("CassStorageService is unavailable temporarily")
            return False

        return await service.write_to_session(cass_msg, timeout=timeout)

    async def write_to_inbox(
        self,
        cass_msg: CassMsgRequest,
        *,
        hash_key: str,
        timeout: int | float,
    ):
        service: Optional[CassMessageService] = self.cass_message_service_getter(
            hash_key=hash_key
        )
        if service is None:
            self.logger.warning("CassStorageService is unavailable temporarily")
            return False

        return await service.write_to_inbox(cass_msg, timeout=timeout)


async def serve(
    proc: WorkerProcess, grpc_manager: GrpcClientManager, app_setting: Optional[dict]
):
    from rpc.cass_storage_service import CassMessageService
    # from rpc.push_service import PushService  # in DownstreamTransferService
    from rpc.transfer_service import DownstreamTransferService
    from uvicorn import Config

    config = Config(app=None, log_level=10)
    del config

    get_running_loop().set_debug(True)
    curr_task = current_task()
    waiter = Future()
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

    platform_id = proc.proc_manager.platform_id
    app_setting["PLATFORM_ID"] = platform_id
    app_setting["APPID"] = app_setting["APPID_PREFIX"] + "X" * 48
    app_setting["CONSUMER_GROUP_NAME"] = f"consumer-group-{platform_id}"

    redis_client = RedisClient()
    rmq_pusher = RMQPusher(app_setting, use_dlq=True, use_read_model=True)
    worker = OutboxWorker(
        app_setting,
        grpc_manager,
        redis_client,
        rmq_pusher,
    )
    async with AsyncExitStack() as exitstack:
        await exitstack.enter_async_context(redis_client)
        await exitstack.enter_async_context(rmq_pusher)
        await exitstack.enter_async_context(grpc_manager)
        await exitstack.enter_async_context(worker)
        install_signal_handlers(handle_exit)
        await waiter
        print("Begin to exit...")
