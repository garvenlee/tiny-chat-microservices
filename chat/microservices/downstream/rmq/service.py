from uuid import uuid4
from logging import getLogger
from typing import AsyncContextManager, Callable, Coroutine, Optional
from contextlib import suppress
from itertools import repeat, cycle

from asyncio import CancelledError, Future, get_running_loop, wait
from aiomisc import asyncretry
from aio_pika.message import IncomingMessage

from chatp.rmq.pika.backend import RMQBackend
from chatp.rmq.pika.consumer import RMQConsumer
from chatp.rmq.pika.producer import BrokerMessage

logger = getLogger("RMQService")
logger.setLevel(10)


class RMQService(AsyncContextManager):
    consumer: RMQConsumer

    def __init__(self, setting: dict) -> None:
        self.setting = setting

    @asyncretry(pause=1, max_tries=3)
    async def send_to_push(
        self,
        entity: bytes,
        *,
        user_id: str,
        app_id: str,
        task_id: Optional[bytes] = None,
        timeout: int | float = 5,
    ):
        if task_id is None:
            task_id = uuid4().hex
        broker = next(self.push_pubs)
        await broker.kick(
            BrokerMessage(
                user_id=user_id,
                app_id=app_id,
                task_id=task_id,
                task_name="PushToService",
                entity=entity,
            ),
            timeout=timeout,
        )
        logger.info("Send one message to push_channel successfully")

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
            # PushService AsyncNotify Queue
            push_pub_factory = backend.create_producer(
                exchange_name=setting["PUSH_EVENT_EXCHANGE_NAME"],
                exchange_type=setting["PUSH_EVENT_EXCHANGE_TYPE"],
                routing_key=setting["PUSH_EVENT_ROUTING_KEY"],
            )
            task_factory = get_running_loop().create_task
            tasks = [
                task_factory(push_pub_factory())
                for _ in repeat(None, setting["NUM_MESSAGE_PUBS"])
            ]
            done, _ = await wait(tasks)
            push_pubs = [task.result() for task in done]
            await push_pubs[-1].bind_queue(
                setting["PUSH_EVENT_QUEUE_NAME"], setting["PUSH_EVENT_ROUTING_KEY"]
            )
            self.push_pubs = cycle(push_pubs)

            # Consumer on ReadModelNotify
            consumer_factory = self._backend.create_consumer(
                queue_name=setting["READ_MODEL_EVENT_QUEUE_NAME"],
                routing_key="1",  # routing_key is the weight
                exchange_name=setting["READ_MODEL_EVENT_EXCHANGE_NAME"],
                exchange_type=setting["READ_MODEL_EVENT_EXCHANGE_TYPE"],
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
