import sys
from logging import getLogger
from enum import StrEnum
from typing import AsyncContextManager
from asyncio import create_task, sleep, wait
from anyio import create_task_group
from aio_pika import IncomingMessage

from chatp.rmq.backend import RMQBackend, RMQStreamBackend
from chatp.rmq.consumer import RMQConsumer
from chatp.rmq.model import ConsumerMessage


class RabbitQueueType(StrEnum):
    PLAIN_QUEUE = "plain"
    STREAM_QUEUE = "stream"


class RMQWorker(AsyncContextManager):
    consumers: list[RMQConsumer]
    backend: RMQBackend | RMQStreamBackend

    def __init__(
        self,
        setting: dict,
        *,
        use_timer: bool = False,
        queue_type: RabbitQueueType = RabbitQueueType.PLAIN_QUEUE,
    ):
        match queue_type:
            case RabbitQueueType.PLAIN_QUEUE:
                self.backend = RMQBackend(
                    host=setting["RMQ_HOST"],
                    port=setting["RMQ_PORT"],
                    username=setting["RMQ_USERNAME"],
                    password=setting["RMQ_PASSWORD"],
                    max_connections=setting["RMQ_CONN_MAX_SIZE"],
                    max_channels=setting["RMQ_CHANNEL_MAX_SIZE"],
                )
            case RabbitQueueType.STREAM_QUEUE:
                self.backend = RMQStreamBackend(
                    host=setting["RMQ_STREAM_HOST"],
                    port=setting["RMQ_STREAM_PORT"],
                    username=setting["RMQ_STREAM_USERNAME"],
                    password=setting["RMQ_STREAM_PASSWORD"],
                )
            case _:
                raise Exception("queue_type must be supported by RabbitQueueType")

        self.setting = setting
        self.use_timer = use_timer
        self.queue_type = queue_type
        self.logger = logger = getLogger("RMQWorker")
        logger.setLevel(10)

        # Statistic Info
        self.total_count = 0
        self.succeed_count = 0
        self.failed_count = 0

    def validate_source(self, message: IncomingMessage) -> bool:
        return message.app_id.startswith(self.setting["APPID_PREFIX"])

    async def discard_message(self, message: ConsumerMessage) -> bool:
        self.logger.warning("Invalid Message Source")
        if not await message.reject(requeue=False):
            self.logger.exception("Found exception when reject one message.")

    async def __aenter__(self):
        await self.backend.__aenter__()

        try:
            await self.initialize()
        except:
            await self.backend.__aexit__(*sys.exc_info())
            raise

        self._run_task = create_task(self.run())
        if self.use_timer:
            self._timer = create_task(self.default_timer())

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        run_task, self._run_task = self._run_task, None
        run_task.cancel()

        tasks = [run_task]
        if self.use_timer:
            timer, self._timer = self._timer, None
            timer.cancel()
            tasks.append(timer)
        await wait(tasks)

        logger = self.logger
        logger.info("run_task has been cancelled, then is ready to close underlaying backend")
        await self.backend.__aexit__(exc_tp, exc_val, exc_tb)
        logger.info("underlaying backend has been closed safely")

    async def default_timer(self):
        logger_info = self.logger.info
        while True:
            await sleep(5)
            logger_info(
                "Running: "
                f"succeed_count {self.succeed_count}, failed_count {self.failed_count}."
            )

    async def initialize(self):
        ...

    async def handler(self, consumer: RMQConsumer):
        ...

    async def run(self):
        handler = self.handler
        # run_task.cancel -> cancel tasks in this scope and wait them to complete
        async with create_task_group() as tg:
            for consumer in self.consumers:
                tg.start_soon(handler, consumer)

    # async def run(self):
    #     handler = self.handler
    #     tasks = [handler(consumer) for consumer in self.consumers]
    #     fut = gather(*tasks, loop=self.loop)  # gather.camcel -> cancel all tasks
    #     try:
    #         await fut
    #     except CancelledError:
    #         await wait(fut._children)  # wait to cancel consume
