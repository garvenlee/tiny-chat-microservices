from enum import IntEnum
from typing import Callable, Optional, NamedTuple
from collections import deque
from attrs import define

from asyncio import TimerHandle, BaseEventLoop
from google.protobuf.message import Message as ProtobufMessage


class MessageWrapper(NamedTuple):
    msg_data: ProtobufMessage
    first_sent_time: float


class DeliveryState(IntEnum):
    ACKED = 0
    LOST = 1
    EXPIRED = 2


MAX_INT64 = 2 << 63


@define(slots=True)
class OutboundMessageLog:
    sender_id: int
    receiver_id: int
    session_id: str
    delivery_id: Optional[int] = None

# delivery_id starts from 1, until 2^63 - 1
class MessageSender:
    __slots__ = (
        "_loop",
        "timers",
        "request_timeout",
        "timeout_handler",
        "pending_ids",
        "delivery_id",
        "waiters",
        # "write_handler",
        # "retransmit_interval",
        # "retransmit_timeout",
        # "retransmit_id",
        # "retransmit_task",
    )

    def __init__(
        self,
        request_timeout: int | float,
        *,
        loop: BaseEventLoop,
    ):
        self._loop = loop
        self.timers: dict[int, TimerHandle] = dict()

        self.request_timeout = request_timeout
        self.timeout_handler: Optional[Callable[[OutboundMessageLog], None]] = None

        # generate local seq
        self.delivery_id: int = 0
        self.pending_ids: deque[int] = deque()
        self.waiters: dict[int, OutboundMessageLog] = {}

    def borrow_virtual_local_id(self):
        delivery_id = (self.delivery_id + 1) % MAX_INT64
        self.delivery_id = delivery_id
        return delivery_id

    def write(self, message: OutboundMessageLog) -> int:
        delivery_id = (self.delivery_id + 1) % MAX_INT64
        self.delivery_id = delivery_id

        message.delivery_id = delivery_id
        self.waiters[delivery_id] = message
        # self.pending_ids.append(delivery_id)
        return delivery_id

    def on_timeout(self, delivery_id: int):
        message = self.waiters.pop(delivery_id, None)
        self.timeout_handler(message)
        self.timers.pop(delivery_id)

    def start_expire_timer(self, delivery_id: int):
        self.timers[delivery_id] = self._loop.call_later(
            self.request_timeout, self.on_timeout, delivery_id
        )
