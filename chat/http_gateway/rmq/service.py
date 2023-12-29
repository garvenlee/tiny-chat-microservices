from uuid import uuid4
from itertools import repeat, cycle
from typing import AsyncContextManager, Iterator, Optional
from asyncio import get_running_loop, wait, gather
from aiomisc.backoff import asyncretry

from chatp.rmq.pika.backend import RMQBackend
from chatp.rmq.pika.producer import RMQProducer
from chatp.rmq.pika.model import BrokerMessage

# from opentelemetry.instrumentation.aio_pika import AioPikaInstrumentor


class RMQService(AsyncContextManager):
    def __init__(
        self,
        setting: dict,
    ) -> None:
        self.setting = setting

        self.email_pubs: Iterator[RMQProducer]
        self.friend_pubs: Iterator[RMQProducer]

    @asyncretry(pause=1, max_tries=3)
    async def publish_email(
        self,
        entity: bytes,
        user_id: str,
        app_id: str,
        task_id: Optional[bytes] = None,
    ):
        if task_id is None:
            task_id = uuid4().hex
        broker = next(self.email_pubs)
        await broker.kick(
            BrokerMessage(
                user_id=user_id,
                app_id=app_id,
                task_id=task_id,
                task_name="RegisterEmail",
                entity=entity,
            )
        )

    @asyncretry(pause=1, max_tries=3)
    async def publish_friend_request(
        self,
        entity: bytes,
        user_id: str,
        app_id: str,
        task_id: Optional[bytes] = None,
    ):
        if task_id is None:
            task_id = uuid4().hex
        broker = next(self.friend_pubs)
        await broker.kick(
            BrokerMessage(
                user_id=user_id,
                app_id=app_id,
                task_id=task_id,
                task_name="FriendRequest",
                entity=entity,
            )
        )

    @asyncretry(pause=1, max_tries=3)
    async def publish_friend_confirm(
        self,
        entity: bytes,
        user_id: str,
        app_id: str,
        task_id: Optional[bytes] = None,
    ):
        if task_id is None:
            task_id = uuid4().hex
        broker = next(self.friend_pubs)
        await broker.kick(
            BrokerMessage(
                user_id=user_id,
                app_id=app_id,
                task_id=task_id,
                task_name="FriendConfirm",
                entity=entity,
            )
        )

    async def __aenter__(self):
        # AioPikaInstrumentor().instrument()
        self._loop = loop = get_running_loop()
        create_task = loop.create_task

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
            # UserRegister Email
            email_pub_factory = backend.create_producer(
                exchange_name=setting["EMAIL_EXCHANGE_NAME"],
                exchange_type=setting["EMAIL_EXCHANGE_TYPE"],
                routing_key=setting["EMAIL_ROUTING_KEY"],
            )
            tasks = [
                create_task(email_pub_factory())
                for _ in repeat(None, setting["NUM_EMAIL_PUBS"])
            ]
            done, _ = await wait(tasks)
            email_pubs = [task.result() for task in done]
            await email_pubs[-1].bind_queue(
                setting["EMAIL_QUEUE_NAME"], setting["EMAIL_ROUTING_KEY"]
            )
            self.email_pubs = cycle(email_pubs)

            # FriendRequest & FriendConfirm
            friend_pub_factory = backend.create_producer(
                exchange_name=setting["FRIEND_EXCHANGE_NAME"],
                exchange_type=setting["FRIEND_EXCHANGE_TYPE"],
            )
            tasks = [
                create_task(friend_pub_factory())
                for _ in repeat(None, setting["NUM_FRIEND_PUBS"])
            ]
            done, _ = await wait(tasks)
            friend_pubs = [task.result() for task in done]
            publisher_bind_queue = friend_pubs[-1].bind_queue
            await gather(
                publisher_bind_queue(setting["FRIEND_QUEUE_NAME_TO_POSTGRES"]),
                publisher_bind_queue(setting["FRIEND_QUEUE_NAME_TO_PUSH"]),
            )
        except BaseException as exc:
            await self._backend.__aexit__(exc.__class__, exc, exc.__traceback__)
            raise
        else:
            self.friend_pubs = cycle(friend_pubs)
        return self

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        await self._backend.__aexit__(exc_tp, exc_val, exc_tb)
