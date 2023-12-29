from typing import Coroutine
from asyncio import BaseEventLoop, Task, wait


class TaskManager:
    def __init__(self, loop: BaseEventLoop):
        self.loop = loop
        self._task_factory = loop.create_task

        self.tasks: set[Task] = set()

    def create_task(self, coro: Coroutine):
        task = self._task_factory(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def wait_for_termination(self):
        if tasks := self.tasks:
            self.tasks = None
            await wait(tasks)
            tasks.clear()

    async def close(self):
        if tasks := self.tasks:
            self.tasks = None
            for task in tasks:
                task.cancel()

            await wait(tasks)
            tasks.clear()
