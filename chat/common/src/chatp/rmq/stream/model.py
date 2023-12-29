from time import monotonic
from typing import NamedTuple
from rstream.amqp import AMQPMessage
from rstream.consumer import MessageContext
from chatp.message.queue import AckQueue

RBFLY_ENGINE = "rbfly"
RSTREAM_ENGINE = "rstream"


class InterfaceError(Exception):
    pass


class OffsetRecord:
    __slots__ = (
        "stream",
        "queue",
        "storing_offset",
        "last_stored_offset",
        "last_stored_time",
        "_is_frozen",
    )

    def __init__(self, stream: str, offset: int):
        self.stream = stream

        self.queue = queue = AckQueue()
        queue.add(offset)

        self.storing_offset = -1
        self.last_stored_offset = offset
        self.last_stored_time = monotonic()

        self._is_frozen = True

    def add(self, offset: int):
        self.queue.add(offset)

    def freeze(self):
        self._is_frozen = True
        self.queue.clear()  # make sure record is in new state

    def unfreeze(self):
        self._is_frozen = False
        self.queue.clear()  # discard useless memory

    @property
    def expected_offset(self):
        return self.queue.first_end

    @property
    def frozen(self):
        return self._is_frozen

    @property
    def is_storing_offset(self):
        return self.storing_offset >= 0


class StreamMessage(NamedTuple):
    body: AMQPMessage
    context: MessageContext
    record: OffsetRecord

    # Here, dont check record.frozon for better performance
    # 1.subscriber is active in most time, so it's a waste of CPU with such an inspection
    # 2.when subscriber is inactive, its record is frozen, in which queue has been cleaned up.
    # But there may still some inflight tasks, and after they are done, StreamMessage.ack will
    # update the offset in record, which causes dirty data. So it's safe to clear the queue
    # when subscriber becomes active.
    #
    # The current implementation of `consumer_update_listener` ignores inflight tasks when
    # subscriber is found inactive, in order to make the state change fast. But it's likely to
    # leak some memory in record.queue, and it's cleaned up only when subscriber becomes active.
    def ack(self):
        self.record.add(self.context.offset)

    @property
    def stream(self):
        return self.record.stream

    @property
    def offset(self):
        return self.context.offset

    @property
    def frozen(self):
        return self.record.frozen
