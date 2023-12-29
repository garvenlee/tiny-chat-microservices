from typing import Callable, Optional, Coroutine, Any
from aio_pika.abc import ExchangeType

from .producer import RMQProducer
from .consumer import RMQConsumer
from .connection import RMQConnector
from .model import StaticTopology


class RMQBackend:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        username: str = "guest",
        password: str = "guest",
        max_connections: int,
        max_channels: int,
        **connection_kwargs: Any,
    ):
        connection_kwargs.update(
            {"host": host, "port": port, "username": username, "password": password}
        )
        self._connector = RMQConnector(
            max_connections, max_channels, **connection_kwargs
        )

    async def __aenter__(self):
        await self._connector.initialize()
        return self

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        connector, self._connector = self._connector, None
        await connector.close()

    def create_producer(
        self,
        exchange_name: str = "chatp",
        exchange_type: ExchangeType = ExchangeType.TOPIC,
        *,
        routing_key: str = "",
    ) -> Callable[[], Coroutine[None, None, RMQProducer]]:
        topo = StaticTopology(exchange_type, exchange_name, routing_key)
        channel_factory = self._connector.get_channel

        async def create_factory():
            publisher = RMQProducer(topo)
            channel = await channel_factory()
            await publisher.startup(channel)
            return publisher

        return create_factory

    def create_consumer(
        self,
        queue_name: str = "chatp",
        *,
        routing_key: Optional[str] = None,
        exchange_name: str = "chatp",
        exchange_type: ExchangeType = ExchangeType.TOPIC,
        # auto_delete: bool = False,
    ) -> Callable[[int], Coroutine[None, None, RMQConsumer]]:
        topo = StaticTopology(exchange_type, exchange_name, routing_key, queue_name)
        channel_factory = self._connector.get_channel

        async def create_factory(initial_qos: int = 1):
            consumer = RMQConsumer(topo, initial_qos=initial_qos)
            channel = await channel_factory()
            await consumer.startup(channel)
            return consumer

        return create_factory
