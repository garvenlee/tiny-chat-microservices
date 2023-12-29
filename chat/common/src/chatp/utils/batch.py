from enum import IntEnum
from typing import Any, Optional
from collections import deque
from itertools import repeat

from asyncio import (
    Future,
    BaseEventLoop,
    TimeoutError,
    CancelledError,
    wait_for,
    get_running_loop,
)


class CapacityState(IntEnum):
    ZERO_BATCH = 0
    ONE_BATCH = 1
    MULTI_BATCH = 2


ZERO_BATCH = CapacityState.ZERO_BATCH
ONE_BATCH = CapacityState.ONE_BATCH
MULTI_BATCH = CapacityState.MULTI_BATCH


class BatchedQueue:
    def __init__(
        self,
        batch_size: int,
        tolerate_rate: float = 0.8,
        sleep_time: float = 0.01,  # 10ms
        loop: Optional[BaseEventLoop] = None,
    ):
        self.batch_size = batch_size
        self.low_water = max(int(batch_size * tolerate_rate), 1)
        self.sleep_time = sleep_time

        if loop is None:
            loop = get_running_loop()
        self._loop = loop

        self._queue = deque()

    def feed_data(self, item: Any):
        queue = self._queue
        queue.append(item)
        if (waiter := self.waiter) is not None:
            if (
                (state := self.state) is ONE_BATCH and len(queue) >= self.low_water
            ) or state is ZERO_BATCH:
                waiter.set_result(None)
                self.waiter = None

    def exhaust(self):
        queue = self._queue
        queue_popleft = queue.popleft
        item = None
        while queue:
            item = queue_popleft()
        return item

    async def partition(self):
        queue = self._queue
        queue_popleft = queue.popleft

        batch_size, low_water = self.batch_size, low_water
        sleep_time = self.sleep_time
        loop = self._loop
        while True:
            if (length := len(queue)) >= batch_size:
                yield (queue_popleft() for _ in repeat(None, batch_size)), batch_size
            elif length:
                self.state = ONE_BATCH
                try:
                    self.waiter = waiter = Future()
                    await wait_for(waiter, timeout=sleep_time, loop=loop)
                except TimeoutError:
                    pass

                length = min(len(queue), batch_size)
                yield (queue_popleft() for _ in repeat(None, length)), length
            else:  # still no data
                self.state = ZERO_BATCH
                try:
                    self.waiter = waiter = Future()
                    await waiter  # wait for ready
                except CancelledError:  # needs to exit
                    # then some messages need to be nacked
                    break
