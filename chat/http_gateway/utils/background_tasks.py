from functools import partial
from typing import Coroutine, Callable, Optional, Any
from asyncio import create_task, wait, Future, Task


def callback_wrapper(
    success_cb: Optional[Callable[[Any], None]],
    error_cb: Optional[Callable[[BaseException], None]],
    pop_from_tasks: Callable[[], None],
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

        pop_from_tasks()

    return _impl


class BackgroundTaskManager:
    __slots__ = "_tasks", "_tasks_discard"

    def __init__(self):
        self._tasks: set[Task] = set()
        self._tasks_discard = self._tasks.discard

    def create_task(
        self,
        coro: Coroutine,
        success_cb: Optional[Callable[[Any], None]] = None,
        error_cb: Optional[Callable[[BaseException], None]] = None,
    ):
        task = create_task(coro)
        self._tasks.add(task)

        if success_cb or error_cb:
            task.add_done_callback(
                callback_wrapper(
                    success_cb,
                    error_cb,
                    pop_from_tasks=partial(self._tasks_discard, task),
                )
            )
        else:
            task.add_done_callback(lambda _: self._tasks_discard(task))

    async def close(self):
        tasks, self._tasks = self._tasks, None
        if tasks:
            for task in tasks:
                task.cancel()
            await wait(tasks)
