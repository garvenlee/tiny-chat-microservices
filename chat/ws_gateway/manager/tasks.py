# from weakref import WeakValueDictionary
from typing import Coroutine, Callable, Optional, Any
from asyncio import create_task, wait, Future, Task


def callback_wrapper(
    success_cb: Optional[Callable[[Any], None]],
    error_cb: Optional[Callable[[BaseException], None]],
):
    def _impl(fut: Future):
        if fut.cancelled():
            # just ignored CancelledError (process shutdown)
            pass
        elif (exc := fut._exception) is not None:
            if error_cb is not None:
                error_cb(exc)
        elif success_cb is not None:
            success_cb(fut._result)

    return _impl


class TaskManager:
    __slots__ = "_tasks", "_tasks_pop"

    def __init__(self):
        self._tasks: dict[int, Task] = {}
        self._tasks_pop = self._tasks.pop

    def create_task(
        self,
        task_key: int,
        coro: Coroutine,
        success_cb: Optional[Callable[[Any], None]] = None,
        error_cb: Optional[Callable[[BaseException], None]] = None,
    ) -> Task:
        task = create_task(coro)
        self._tasks[task_key] = task

        if success_cb or error_cb:
            task.add_done_callback(
                callback_wrapper(
                    success_cb,
                    error_cb,
                )
            )
        task.add_done_callback(lambda _: self._tasks_pop(task_key, None))
        return task

    def cancel(self, task_key: int):
        if (task := self._tasks.get(task_key)) is not None:
            task.cancel()
            return True
        return False

    async def close(self):
        if tasks := self._tasks:
            self._tasks = None
            for task in tasks.values():
                task.cancel()
            await wait(tasks)
            tasks.clear()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        await self.close()
