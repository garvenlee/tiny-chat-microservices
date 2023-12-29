import logging
from contextlib import suppress
from asyncio import (
    Queue,
    Future,
    Task,
    CancelledError,
    wait,
    get_running_loop,
    create_task,
)

from chatp.proto.services.push.push_pb2 import PubEventToGateway, ConsumerFeedback
from .model import FAILED_EXCEPTION, ACTIVE

from chatp.utils.types import ServiceAddr

# The type of delivery_id in MsgData is int64, not allowed wrap-around
# but PushChannel uses uint32 for faster data transmission
MAX_INT32 = 2 << 32 - 1

logger = logging.getLogger("EventCollector")


class EventChannel:
    __slots__ = "_queue", "_confirmations", "_delivery_id", "_loop", "state"

    def __init__(self, maxsize: int = 1024):
        self._queue: Queue[tuple[PubEventToGateway, Future]] = Queue(maxsize)
        self._confirmations: dict[int, Future] = {}
        self._delivery_id = 0
        self._loop = get_running_loop()

        self.state = ACTIVE

    async def publish(self, event: PubEventToGateway):
        delivery_id = (self._delivery_id + 1) % MAX_INT32
        event.delivery_id = self._delivery_id = delivery_id
        waiter = Future()
        confirmations = self._confirmations
        confirmations[delivery_id] = waiter  # dict holds the insertion order
        waiter.add_done_callback(lambda _: confirmations.pop(delivery_id, None))

        await self._queue.put((event, waiter))
        return waiter

    def on_delivery(self, feedback: ConsumerFeedback):
        confirmations = self._confirmations
        status, confirm = feedback.status, feedback.confirm

        start_id, end_id = confirm.start_id, confirm.end_id
        for delivery_id in range(start_id, end_id):
            waiter = confirmations.get(delivery_id)
            if waiter is not None and not waiter.done():
                waiter.set_result(status)


class EventCollector:
    def __init__(self):
        self._channels: dict[ServiceAddr, EventChannel] = {}

    def register(self, addr: bytes):
        return self._channels.setdefault(addr, EventChannel())

    async def send(self, event: PubEventToGateway, addr: bytes) -> Future:
        return await self._channels[addr].publish(event)

    async def send_mulitple(
        self, event: PubEventToGateway, *addrs: bytes
    ) -> list[Future]:
        channels = self._channels

        tasks: list[Task[Future]] = []
        for addr in addrs:
            (evt := PubEventToGateway()).CopyFrom(event)
            tasks.append(create_task(channels[addr].publish(evt)))
        done, _ = await wait(tasks)
        return [task.result() for task in done]

    async def dispatch(self, addr: str):
        queue_getter = self._channels[addr]._queue.get
        with suppress(CancelledError):
            while True:
                item = await queue_getter()
                yield item
