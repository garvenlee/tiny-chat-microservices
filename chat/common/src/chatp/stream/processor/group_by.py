from typing import Any, Callable
from collections import defaultdict, deque
from asyncio import Queue, get_running_loop

from .base import Operation


def group(operation: Operation, handler):
    queue = Queue()
    loop = get_running_loop()
    loop.create_task(consumer())

    async def consumer():
        queue_getter = queue.get
        while True:
            item, waiter = await queue_getter()
            result = await handler(item)
            waiter.set_result(result)

    async def inner_handle(arg: Any):
        pass

    return Operation(inner_handle)(operation)


def group_by(key_mapper: Callable):
    def operation_factory(operation: Operation):
        registry = defaultdict(deque)

        def inner_handle(arg: Any):
            key = key_mapper[arg]
            group = registry[key]
            if not group:
                # create task consumes from group
                pass

            registry[key].appendleft(arg)

        return Operation(inner_handle)(operation)

    return operation_factory
