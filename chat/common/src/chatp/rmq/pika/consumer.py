from logging import getLogger
from enum import IntEnum
from typing import Any, Optional, Callable, Coroutine
from contextlib import asynccontextmanager

from aio_pika.robust_channel import RobustChannel
from aio_pika.robust_queue import RobustQueue
from aio_pika.message import IncomingMessage

from .model import StaticTopology

logger = getLogger("RabbitConsumer")


class WorkerState(IntEnum):
    IDLE = 0
    RUNNING = 1  # 001
    CLOSING = 2  # 010
    CLOSED = 6  # 110
    CANCELLING = 8  # 1000
    CANCELLED = 24  # 11000


IDLE = WorkerState.IDLE
RUNNING = WorkerState.RUNNING
CLOSING = WorkerState.CLOSING
CLOSED = WorkerState.CLOSED
CANCELLING = WorkerState.CANCELLING
CANCELLED = WorkerState.CANCELLED


class RMQConsumer:
    __slots__ = (
        "state",
        "topo",
        "qos",
        "read_channel",
        "read_queue",
    )

    def __init__(  # noqa: WPS211
        self,
        topo: StaticTopology,
        initial_qos: int,
    ) -> None:
        self.state = WorkerState.IDLE

        self.topo = topo
        self.qos = initial_qos

        self.read_channel: RobustChannel
        self.read_queue: RobustQueue

    @property
    def exchange_name(self):
        return self.topo.exchange_name

    @property
    def exchange_type(self):
        return self.topo.exchange_type

    @property
    def routing_key(self):
        return self.topo.routing_key

    async def startup(self, read_channel: RobustChannel) -> None:
        exchange_name = self.exchange_name
        await read_channel.declare_exchange(exchange_name, type=self.exchange_type)
        queue = await read_channel.declare_queue(self.topo.queue_name)
        await queue.bind(exchange=exchange_name, routing_key=self.routing_key)

        await read_channel.set_qos(prefetch_count=self.qos)

        self.read_channel = read_channel
        self.read_queue = queue

    async def cancel(self, consumer_tag: str):
        if not self.read_channel.is_closed and not self.state & WorkerState.CANCELLING:
            self.state &= WorkerState.CANCELLING
            await self.read_queue.cancel(consumer_tag)
            self.state &= WorkerState.CANCELLED

    @asynccontextmanager
    async def start_listen(
        self,
        on_consume: Callable[[IncomingMessage], Coroutine],
        on_completed: Optional[Callable[[], Optional[IncomingMessage]]] = None,
    ):
        async def close(*_: Any):
            if read_channel.is_closed:
                return

            read_queue.close_callbacks.remove(close)

            # nack must be after consumer is cancel
            if not self.state & WorkerState.CANCELLING:
                self.state &= WorkerState.CANCELLING
                await read_queue.cancel(consumer_tag)
                self.state &= WorkerState.CANCELLED

            if (
                on_completed is not None
                and (message := on_completed()) is not None
                and not read_channel.is_closed
            ):
                await message.nack(requeue=True, multiple=True)

        read_channel, read_queue = self.read_channel, self.read_queue
        consumer_tag = await read_queue.consume(on_consume)
        read_queue.close_callbacks.add(close)
        self.state = WorkerState.RUNNING
        try:
            yield consumer_tag
        finally:
            self.state &= WorkerState.CLOSING
            await close()
            self.state &= WorkerState.CLOSED
