from functools import partial
from typing import Optional, Any
from inspect import iscoroutinefunction

from mmh3 import hash_bytes as mmh3_hash_bytes
from cachetools import LRUCache

from rstream.utils import MonotonicSeq
from rstream.producer import ConfirmationStatus, MessageT
from rstream.superstream_producer import SuperStreamProducer, CB
from rstream.superstream import Metadata, DefaultSuperstreamMetadata, RoutingStrategy


class HashRoutingMurmurStrategy(RoutingStrategy):
    def __init__(self, routingKeyExtractor: CB[Any]):
        self.partition_cache = LRUCache(maxsize=2**14)
        self.routingKeyExtractor = routingKeyExtractor

    async def route(self, message: MessageT, metadata: Metadata) -> list[str]:
        route_fn = self.routingKeyExtractor
        if iscoroutinefunction(route_fn):
            key = await route_fn(message)
        else:
            key = route_fn(message)
        cache = self.partition_cache
        if (stream := cache.get(key)) is None:
            key_bytes = bytes(key, "UTF-16")
            hash = mmh3_hash_bytes(key_bytes, 104729)

            partitions = await metadata.partitions()
            route = int.from_bytes(hash, "little", signed=False) % len(partitions)
            stream = partitions[route]
            cache[key] = stream

        return stream


class RMQStreamProducer(SuperStreamProducer):
    def __init__(
        self,
        host: str,
        port: int = 5552,
        *,
        username: str,
        password: str,
        super_stream: str,
        broker_name: str,
        routing_extractor: CB[Any],
        default_batch_publishing_delay: float = 0.2,
        connection_closed_handler: Optional[CB[Exception]] = None,
        **extra,
    ):
        super().__init__(
            host,
            port,
            username=username,
            password=password,
            super_stream=super_stream,
            routing_extractor=routing_extractor,
            default_batch_publishing_delay=default_batch_publishing_delay,
            connection_closed_handler=connection_closed_handler,
            **extra,
        )
        self.broker_name = broker_name

        self._send_waiters = {}
        self._sequence_recorder: dict[str, MonotonicSeq] = {}

    async def start(self) -> None:
        self._default_client = await self._pool.get(
            connection_closed_handler=self._connection_closed_handler,
            connection_name="rstream-locator",
        )
        self.super_stream_metadata = DefaultSuperstreamMetadata(
            self.super_stream, self._default_client
        )
        self._routing_strategy = HashRoutingMurmurStrategy(self.routing_extractor)

    # each stream, one publisher, and share the same connection
    async def initialize_producer(self):
        producer = await self._get_producer()
        partitions = await self.super_stream_metadata.partitions()

        sequence_recorder = self._sequence_recorder
        publisher_backbone = f"_publisher_{self.broker_name}"
        for partition in partitions:
            publisher_name = f"{partition}{publisher_backbone}"
            publisher = await producer._get_or_create_publisher(
                partition, publisher_name=publisher_name
            )
            sequence_recorder[partition] = publisher.sequence

    async def startup(self):
        await self.start()
        await self.initialize_producer()

    async def publish_cb_wrapper(
        self,
        confirmation: ConfirmationStatus,
        cb: Optional[CB[tuple[ConfirmationStatus, MessageT]]],
    ):
        message = self._send_waiters.pop(confirmation.message_id, None)
        if message is not None:
            await cb(confirmation, message)

    async def send(
        self,
        message: MessageT,
        on_publish_confirm: Optional[CB[tuple[ConfirmationStatus, MessageT]]] = None,
    ) -> None:
        stream = await self._routing_strategy.route(message, self.super_stream_metadata)

        if on_publish_confirm is not None:
            publishing_id = self._sequence_recorder[stream].next()
            message.publishing_id = publishing_id
            self._send_waiters[publishing_id] = message

            on_publish_confirm = partial(self.publish_cb_wrapper, cb=on_publish_confirm)

        await self._producer.send(
            stream=stream,
            message=message,
            on_publish_confirm=on_publish_confirm,
        )


class RbflyStreamProducer:
    pass
