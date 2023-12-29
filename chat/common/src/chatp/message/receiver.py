from typing import Callable, Optional
from collections import deque

from asyncio import BaseEventLoop, Future, TimerHandle


class MessageReceiver:
    __slots__ = (
        "_loop",
        "pending_queue",
        "ack_delay",
        "ack_waiter",
        "ack_task",
        "ack_timer",
        "ack_handler",
    )

    def __init__(self, ack_delay: int | float, *, loop: BaseEventLoop):
        self._loop = loop

        self.pending_queue = deque()

        self.ack_delay = ack_delay
        self.ack_waiter = Future()
        self.ack_task = loop.create_task(self.schedule_ack())

        self.ack_timer: Optional[TimerHandle] = None
        self.ack_handler: Optional[Callable] = None

    async def schedule_ack(self):
        ack_handler = self.ack_handler
        pending_queue = self.pending_queue
        while True:
            await self.ack_waiter

            ack_handler(pending_queue)
            pending_queue.clear()

            self.ack_waiter = Future()
            self.ack_timer = None

    def start_ack_timer(self):
        if self.ack_timer is None and self.ack_handler is not None:
            self.ack_timer = self._loop.call_later(
                self.ack_delay, lambda: self.ack_waiter.set_result(None)
            )
