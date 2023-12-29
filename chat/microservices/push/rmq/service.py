from logging import getLogger
from contextlib import suppress
from typing import AsyncContextManager, Callable, Coroutine, Optional

from asyncio import CancelledError, Future, get_running_loop, wait
from aio_pika.message import IncomingMessage

from chatp.rmq.pika.backend import RMQBackend
from chatp.rmq.pika.consumer import RMQConsumer


logger = getLogger("RMQService")
logger.setLevel(10)


class RMQService(AsyncContextManager):
    consumer: RMQConsumer

    def __init__(self, setting: dict) -> None:
        self.setting = setting

    async def __aenter__(self):
        setting = self.setting
        self._backend = backend = RMQBackend(
            host=setting["RMQ_HOST"],
            port=setting["RMQ_PORT"],
            username=setting["RMQ_USERNAME"],
            password=setting["RMQ_PASSWORD"],
            max_connections=setting["RMQ_CONN_MAX_SIZE"],
            max_channels=setting["RMQ_CHANNEL_MAX_SIZE"],
        )
        await backend.__aenter__()

        try:
            consumer_factory = self._backend.create_consumer(
                queue_name=setting["PUSH_EVENT_QUEUE_NAME"],
                routing_key=setting["PUSH_EVENT_ROUTING_KEY"],
                # routing_key="1",  # routing_key is the weight
                exchange_name=setting["PUSH_EVENT_EXCHANGE_NAME"],
                exchange_type=setting["PUSH_EVENT_EXCHANGE_TYPE"],
            )
            self.consumer = await consumer_factory(initial_qos=1024)
        except BaseException as exc:
            await self._backend.__aexit__(exc.__class__, exc, exc.__traceback__)
            raise
        else:
            return self

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        await self._backend.__aexit__(exc_tp, exc_val, exc_tb)

    async def run(self, on_consume: Callable[[IncomingMessage], Coroutine]):
        appid_prefix = self.setting["APPID_PREFIX"]
        shutdown = False
        last_seen_message: Optional[IncomingMessage] = None

        async def on_consume_wrapper(message: IncomingMessage):
            nonlocal last_seen_message
            if shutdown:
                last_seen_message = message
                return

            if not message.app_id.startswith(appid_prefix):
                logger.warning("Found invalid message")
                try:
                    await message.reject(requeue=False)
                except BaseException as exc:
                    logger.exception(
                        "Found exception when `reject` one message: %s",
                        exc,
                        exc_info=exc,
                    )
                return

            task = create_task(on_consume(message))
            task.add_done_callback(tasks.discard)
            tasks.add(task)

        tasks = set()
        create_task = get_running_loop().create_task
        async with self.consumer.start_listen(
            on_consume_wrapper, lambda: last_seen_message
        ):
            with suppress(CancelledError):
                await Future()  # cancelled by system

            shutdown = True
            if tasks:
                await wait(tasks)
                tasks.clear()
