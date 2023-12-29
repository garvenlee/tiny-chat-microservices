from typing import Callable, Any
from rstream.superstream_producer import RouteType
from .connection import RMQStreamConnector
from .model import RSTREAM_ENGINE


class RMQStreamBackend:
    def __init__(
        self,
        host: str,
        port: int = 5552,
        *,
        username: str,
        password: str,
        engine: str = RSTREAM_ENGINE,
        **connection_kwargs: Any,
    ):
        connection_kwargs.update(
            {"host": host, "port": port, "username": username, "password": password}
        )
        self._connector = RMQStreamConnector(engine, **connection_kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        connector, self._connector = self._connector, None
        await connector.close()

    async def create_producer(
        self,
        super_stream: str,
        *,
        broker_name: str,
        routing_type: RouteType = RouteType.Hash,
        routing_extractor: Callable,
        default_batch_publishing_delay: float = 0.1,
    ):
        return await self._connector.create_producer(
            super_stream,
            broker_name=broker_name,
            routing_type=routing_type,
            routing_extractor=routing_extractor,
            default_batch_publishing_delay=default_batch_publishing_delay,
        )

    async def create_consumer(self, super_stream: str, *, broker_name: str):
        return await self._connector.create_consumer(super_stream, broker_name)
