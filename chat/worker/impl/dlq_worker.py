from types import FrameType
from typing import Optional, Callable
from time import monotonic
from functools import partial
from contextlib import AsyncExitStack

from asyncio import Future, Event, CancelledError, wait, get_running_loop, current_task
from aio_pika import IncomingMessage

from chatp.proto.services.transfer.msg_data_pb2 import (
    DLQMsgData,
    DLQ_SESSION_ONLY,
    DLQ_INBOX_ONLY,
)
from chatp.proto.services.transfer.cass_storage_pb2 import CassMsgRequest
from chatp.rmq.pika.consumer import RMQConsumer
from chatp.rmq.pika.backend import RMQBackend
from chatp.rmq.pika.model import ConsumerMessage
from chatp.redis.client import RedisClient
from chatp.multiprocess.worker import WorkerProcess
from chatp.manager.grpc_client import GrpcClientManager
from chatp.utils.signals import install_signal_handlers

from .base_worker import RMQWorker
from utils.mixin import PushMixin
from rmq.service import RMQPusher
from rpc.cass_storage_service import CassMessageService


class DLQWorker(RMQWorker, PushMixin):
    backend: RMQBackend

    def __init__(
        self,
        setting: dict,
        grpc_manager: GrpcClientManager,
        rmq_pusher: RMQPusher,
        redis_client: RedisClient,
    ):
        super().__init__(setting)
        super(RMQWorker, self).__init__(
            grpc_manager,
            redis_client,
            rmq_pusher,
            broker_id=setting["APPID"],
        )

        self.cass_message_service_getter: Callable[
            [str], Optional[CassMessageService]
        ] = partial(grpc_manager.find_service, "CassMessageService")
        self.shutdown_event = Event()

    async def initialize(self):
        setting = self.setting
        consumer_factory = self.backend.create_consumer(
            queue_name=setting["DEAD_LETTER_QUEUE_NAME"],
            routing_key="1",
            exchange_name=setting["DEAD_LETTER_EXCHANGE_NAME"],
            exchange_type=setting["DEAD_LETTER_EXCHANGE_TYPE"],
        )

        self.loop = loop = get_running_loop()
        create_task = loop.create_task
        tasks = [create_task(consumer_factory(initial_qos=128))]
        await wait(tasks)
        self.consumers = [task.result() for task in tasks]

        self.logger.info("RMQ Service connected.")

    async def handler(self, consumer: RMQConsumer):
        shutdown = False
        last_seen_message: Optional[IncomingMessage] = None

        def on_consume(pika_message: IncomingMessage) -> None:
            nonlocal shutdown, last_seen_message
            if shutdown:  # dont create new task anymore
                last_seen_message = pika_message
                return

            message = ConsumerMessage(pika_message)
            if not self.validate_source(pika_message):
                task = create_task(self.discard_message(message))
                task.add_done_callback(tasks.discard)
                tasks.add(task)
                return

            # initial_qos makes sure tasks wont be too many
            logger.info("Received one DLQMsgData, ready to handle it...")
            self.total_count += 1

            entity = pika_message.body
            data: DLQMsgData = DLQMsgData.FromString(entity)
            task = create_task(event_handler(data, message))
            task.add_done_callback(tasks.discard)
            tasks.add(task)

        tasks = set()
        create_task = self.loop.create_task
        logger, event_handler = self.logger, self.event_handler
        async with consumer.start_listen(on_consume, lambda: last_seen_message):
            try:
                await self.shutdown_event.wait()
            except CancelledError:
                logger.info(
                    "handler is cancelled, now need to wait inflight tasks done..."
                )
                shutdown = True
                if tasks:
                    await wait(tasks)  # wait all inflight tasks done

    async def event_handler(self, event: DLQMsgData, message: ConsumerMessage):
        rsq_data = event.data
        delivery_id, msg_id = rsq_data.delivery_id, rsq_data.message_id
        msg_data = rsq_data.data
        hash_key = str(msg_data.session_id)
        if (action := event.action) is DLQ_INBOX_ONLY:
            if await self.notify_read_model(
                msg_data, msg_id, delivery_id, hash_key=hash_key, timeout=10
            ):
                await message.ack()
            else:
                await message.reject(requeue=True)

        elif action is DLQ_SESSION_ONLY:
            if await self.write_to_session(
                CassMsgRequest(
                    message_data=msg_data,
                    message_id=msg_id,
                    delivery_id=delivery_id,
                ),
                hash_key=hash_key,
                timeout=12,
            ):
                await message.ack()
            else:
                await message.reject(requeue=True)
        else:
            task = self.task_factory(
                self.write_to_session(
                    CassMsgRequest(
                        message_data=msg_data,
                        message_id=msg_id,
                        delivery_id=delivery_id,
                    ),
                    hash_key=hash_key,
                    timeout=12,
                )
            )
            if (
                await self.notify_read_model(
                    msg_data, msg_id, delivery_id, hash_key=hash_key, timeout=10
                )
                and await task
            ):
                await message.ack()
            else:
                await message.reject(requeue=True)

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

        # extra function call and result convert
        return await service.write_to_session(cass_msg, timeout=timeout)


async def serve(
    proc: WorkerProcess, grpc_manager: GrpcClientManager, app_setting: Optional[dict]
):
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

    app_setting["APPID"] = app_setting["APPID_PREFIX"] + "X" * 48
    app_setting["DEAD_LETTER_QUEUE_NAME"] = (
        app_setting["DEAD_LETTER_QUEUE_NAME_PREFIX"] + proc.proc_manager.platform_id
    )

    redis_client = RedisClient()
    rmq_pusher = RMQPusher(app_setting, use_dlq=False, use_read_model=True)
    worker = DLQWorker(app_setting, grpc_manager, rmq_pusher, redis_client)
    async with AsyncExitStack() as exitstack:
        await exitstack.enter_async_context(redis_client)
        await exitstack.enter_async_context(rmq_pusher)
        await exitstack.enter_async_context(grpc_manager)
        await exitstack.enter_async_context(worker)
        install_signal_handlers(handle_exit)
        await waiter
        print("Begin to exit...")
