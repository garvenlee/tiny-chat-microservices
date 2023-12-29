from logging import getLogger
from uuid import uuid4
from itertools import repeat, cycle
from typing import AsyncContextManager, Optional

from asyncio import get_running_loop, wait
from aiomisc import asyncretry

from chatp.rmq.pika.backend import RMQBackend
from chatp.rmq.pika.model import BrokerMessage

logger = getLogger("RMQPusher")
logger.setLevel(10)


class RMQPusher(AsyncContextManager):
    def __init__(
        self, setting: dict, use_dlq: bool, use_read_model: bool = False
    ) -> None:
        self.setting = setting
        self.use_dlq = use_dlq
        self.use_read_model = use_read_model

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

    @asyncretry(pause=1, max_tries=3)
    async def send_to_read_model(
        self,
        entity: bytes,
        *,
        hash_key: str,
        user_id: str,
        app_id: str,
        task_id: Optional[bytes] = None,
        timeout: int | float = 5,
    ):
        if task_id is None:
            task_id = uuid4().hex
        broker = next(self.read_model_pubs)
        await broker.kick(
            BrokerMessage(
                user_id=user_id,
                app_id=app_id,
                task_id=task_id,
                task_name="SendToReadModel",
                entity=entity,
            ),
            routing_key=hash_key,
            timeout=timeout,
        )
        logger.info("Send one message to read_model successfully")

    @asyncretry(pause=1, max_tries=3)
    async def send_to_dlq(
        self,
        entity: bytes,
        *,
        hash_key: str,
        user_id: str,
        app_id: str,
        task_id: Optional[bytes] = None,
        timeout: int | float = 5,
    ):
        if task_id is None:
            task_id = uuid4().hex
        broker = next(self.dlq_pubs)
        await broker.kick(
            BrokerMessage(
                user_id=user_id,
                app_id=app_id,
                task_id=task_id,
                task_name="SendToDLQ",
                entity=entity,
            ),
            routing_key=hash_key,
            timeout=timeout,
        )
        logger.info("Send one message to dlq successfully")

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

        self._loop = loop = get_running_loop()
        task_factory = loop.create_task

        try:
            if self.use_read_model:
                # DownstreamService ReadModel Queue
                read_model_pub_factory = backend.create_producer(
                    exchange_name=setting["READ_MODEL_EVENT_EXCHANGE_NAME"],
                    exchange_type=setting["READ_MODEL_EVENT_EXCHANGE_TYPE"],
                    routing_key="1",  # weight, here is nouse
                )
                tasks = [
                    task_factory(read_model_pub_factory())
                    for _ in repeat(None, setting["NUM_READ_MODEL_PUBS"])
                ]
                done, _ = await wait(tasks)
                read_model_pubs = [task.result() for task in done]
                self.read_model_pubs = cycle(read_model_pubs)

            else:
                # PushService AsyncNotify Queue
                push_pub_factory = backend.create_producer(
                    exchange_name=setting["PUSH_EVENT_EXCHANGE_NAME"],
                    exchange_type=setting["PUSH_EVENT_EXCHANGE_TYPE"],
                    routing_key=setting["PUSH_EVENT_ROUTING_KEY"],
                )
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

            if self.use_dlq:
                # MessageConsumer DLQ
                dlq_pub_factory = backend.create_producer(
                    exchange_name=setting["DEAD_LETTER_EXCHANGE_NAME"],
                    exchange_type=setting["DEAD_LETTER_EXCHANGE_TYPE"],
                    routing_key="1",  # weight, here is nouse
                )
                tasks = [
                    task_factory(dlq_pub_factory())
                    for _ in repeat(None, setting["NUM_DLQ_PUBS"])
                ]
                done, _ = await wait(tasks)
                dlq_pubs = [task.result() for task in done]
                self.dlq_pubs = cycle(dlq_pubs)

        except BaseException as exc:
            await self._backend.__aexit__(exc.__class__, exc, exc.__traceback__)
            raise
        else:
            return self

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        await self._backend.__aexit__(exc_tp, exc_val, exc_tb)
