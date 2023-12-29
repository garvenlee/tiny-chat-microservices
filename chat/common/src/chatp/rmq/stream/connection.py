from logging import getLogger
from enum import IntEnum
from typing import Callable, Union
from rstream.superstream_producer import RouteType
from .producer import RMQStreamProducer, RbflyStreamProducer
from .consumer import RMQStreamConsumer, RbflyStreamConsumer
from .model import InterfaceError, RBFLY_ENGINE, RSTREAM_ENGINE

logger = getLogger("RabbitConnector")


class StreamConnectionState(IntEnum):
    IDLE = 0
    CONNECTED = 1
    CONNECTING = 2
    CLOSED = 3


STREAM_IDLE = StreamConnectionState.IDLE
STREAM_CONNECTED = StreamConnectionState.CONNECTED
STREAM_CONNECTING = StreamConnectionState.CONNECTING
STREAM_CLOSED = StreamConnectionState.CLOSED


class RMQStreamConnector:
    def __init__(self, engine: str, **conn_kwargs):
        self.engine = engine
        self.conn_kwargs = conn_kwargs

        if engine == RSTREAM_ENGINE:  # default currently
            self.producer_factory = RMQStreamProducer
            self.consumer_factory = RMQStreamConsumer
        elif engine == RBFLY_ENGINE:  # rbfly doesn't implement superstream currently
            self.producer_factory = RbflyStreamProducer
            self.consumer_factory = RbflyStreamConsumer
        else:
            raise InterfaceError("engine must be `RSTREAM_ENGINE` or `RBFLY_ENGINE`.")

        self.worker: Union[RMQStreamProducer, RMQStreamConsumer] = None
        self.state = STREAM_IDLE

    async def close(self):
        if (worker := self.worker) is not None:
            self.state = STREAM_CLOSED
            await worker.close()

    # means certain client countered OSError - write_frame or read_frame
    async def on_closed(self, exc: BaseException):
        logger.warning("on_closed is triggered, due to %s", exc, exc_info=True)
        if self.state is STREAM_CLOSED:
            return

        self.state = STREAM_CLOSED
        try:
            await self.worker.close()
        except BaseException as exc:
            logger.exception("Found exc in on_closed: %s", exc, exc_info=exc)
        finally:
            self.state = STREAM_CONNECTING
            await self.worker.startup()
            self.state = STREAM_CONNECTED

    async def create_producer(
        self,
        super_stream: str,
        *,
        broker_name: str,
        routing_type: RouteType,
        routing_extractor: Callable,
        default_batch_publishing_delay: float = 0.1,
    ):
        if self.worker is not None:
            raise InterfaceError("StreamConnector already has a worker.")

        producer = RMQStreamProducer(
            super_stream=super_stream,
            broker_name=broker_name,
            routing=routing_type,
            routing_extractor=routing_extractor,
            default_batch_publishing_delay=default_batch_publishing_delay,
            connection_closed_handler=self.on_closed,
            **self.conn_kwargs,
        )

        self.state = STREAM_CONNECTING
        await producer.startup()
        self.state = STREAM_CONNECTED

        self.worker = producer
        return producer

    async def create_consumer(self, super_stream: str, consumer_group_name: str):
        if self.worker is not None:
            raise InterfaceError("StreamConnector already has a worker.")

        consumer = RMQStreamConsumer(
            super_stream=super_stream,
            consumer_group_name=consumer_group_name,
            connection_closed_handler=self.on_closed,
            **self.conn_kwargs,
        )

        self.state = STREAM_CONNECTING
        await consumer.startup()
        self.state = STREAM_CONNECTED

        self.worker = consumer
        return consumer
