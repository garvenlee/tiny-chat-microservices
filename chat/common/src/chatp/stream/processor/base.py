from functools import wraps, reduce
from typing import Any, Callable, Awaitable, Union
from asyncio import iscoroutinefunction


class UnimplementedError(Exception):
    pass


def async_wrapper(func: Callable[[Any], Any]) -> Any:
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def awaitable(func: Callable[[Any], Awaitable[Any]]):
    if not callable(func):
        raise Exception(
            "Operation.handle must be a function, returns an Awaitable Object."
        )
    elif iscoroutinefunction(func):
        return func
    else:
        return async_wrapper(func)


class Operation:
    __slots__ = "_handle", "is_async"

    def __init__(self, handle: Callable[[Any], Awaitable[Any]]):
        self._handle = handle
        self.is_async = iscoroutinefunction(handle)

    def frozen(self, arg: Any) -> tuple[Union[Awaitable[Any], Any], bool]:
        return self._handle(arg), self.is_async

    def pipe(self, *operations: "Operation"):
        inner_operation = self
        for outer_operation in operations:
            inner_operation = inner_operation(outer_operation)
        return inner_operation

    def __call__(self, operation: "Operation"):
        async def _async_async(arg: Any):
            return await outer_handle(await inner_handle(arg))

        async def _async_sync(arg: Any):
            return outer_handle(await inner_handle(arg))

        async def _sync_async(arg: Any):
            return await outer_handle(inner_handle(arg))

        def _sync_sync(arg: Any):
            return outer_handle(inner_handle(arg))

        inner_handle, inner_is_async = self._handle, self.is_async
        outer_handle, outer_is_async = operation._handle, operation.is_async

        if outer_is_async and inner_is_async:
            return Operation(_async_async)
        elif outer_is_async:
            return Operation(_sync_async)
        elif inner_is_async:
            return Operation(_async_sync)
        else:
            return Operation(_sync_sync)
