from collections import defaultdict
from typing import Optional, Callable, Iterable, Any
from asyncio import get_running_loop, BaseEventLoop

from .sender import MessageSender, OutboundMessageLog
from .receiver import MessageReceiver
from .queue import AckQueue


class MessageStream:
    def __init__(
        self,
        request_timeout: int | float,
        ack_delay: int | float,
        *,
        loop: Optional[BaseEventLoop] = None,
    ):
        if loop is None:
            loop = get_running_loop()

        self.sender = MessageSender(request_timeout, loop=loop)
        self.receiver = MessageReceiver(ack_delay, loop=loop)

        # used to filter
        self.operation_log: defaultdict[int, AckQueue] = defaultdict(AckQueue)

    def bind_timeout_handler(self, handler: Callable[[OutboundMessageLog], None]):
        self.sender.timeout_handler = handler

    def bind_ack_handler(self, handler: Callable[[Iterable], None]):
        self.receiver.ack_handler = handler

    def write(self, message: OutboundMessageLog) -> int:
        sender = self.sender
        delivery_id = message.delivery_id
        if delivery_id is None:
            delivery_id = sender.write(message)
        else:
            waiters = sender.waiters
            if delivery_id in waiters:
                raise Exception("delivery_id must be unique.")
            waiters[delivery_id] = message

        sender.start_expire_timer(delivery_id)
        return delivery_id

    def read(self, log: Any):
        receiver = self.receiver
        receiver.pending_queue.append(log)
        receiver.start_ack_timer()

    def on_processed(self, channel_number: int, delivery_id: int):
        if delivery_id not in self.operation_log[channel_number]:
            self.operation_log[channel_number].add(delivery_id)

    def on_acked(self, delivery_id: int):  # sent message was acked
        sender = self.sender
        sender.waiters.pop(delivery_id, None)
        timer = sender.timers.pop(delivery_id, None)
        if timer is not None:
            timer.cancel()
