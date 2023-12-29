from asyncio import BaseEventLoop, Task, get_event_loop, gather
from types import CoroutineType
from typing import Union, Coroutine
from contextlib import suppress

from asyncio import Handle, CancelledError


class TaskManager:
    def __init__(self, loop: BaseEventLoop):
        if loop is None:
            loop = get_event_loop()
        self._loop = loop
        self._tasks: set[Task] = set()
        self._handles: set[Handle] = set()
        self._idle_coros: set[Coroutine] = set()

    def create_task(self, coro: CoroutineType):
        task = self._loop.create_task(coro)
        tasks = self._tasks
        tasks.add(task)
        task.add_done_callback(lambda _: tasks.discard(task))
        return task

    def create_timer(self, delay: Union[float, int], coro: Coroutine):
        def wrapper():
            task = self.create_task(coro)
            task.add_done_callback(handles.discard(handle))
            idle_coros.discard(coro)

        handle = self._loop.call_later(delay, wrapper)
        handles = self._handles
        handles.add(handle)
        idle_coros = self._idle_coros
        idle_coros.add(coro)

    async def close(self):
        if idle_coros := self._idle_coros:
            self._idle_coros = None
            exc = CancelledError()
            for coro in idle_coros:
                with suppress(CancelledError):
                    coro.throw(exc)

        if handles := self._handles:
            self._handles = None
            for handle in handles:
                handle.cancel()

        if tasks := self._tasks:
            self._tasks = None
            for task in tasks:
                task.cancel()
            await gather(*tasks, return_exceptions=True)
