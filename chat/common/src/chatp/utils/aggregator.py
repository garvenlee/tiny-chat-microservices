from logging import getLogger
from time import monotonic
from typing import (
    Optional,
    Awaitable,
    Callable,
    Iterable,
    List,
    Any,
)
from functools import partial
from types import FunctionType
from collections import deque
from asyncio import (
    BaseEventLoop,
    TimeoutError,
    Event,
    Future,
    wait_for,
    get_running_loop,
)


log = getLogger(__name__)


class ExecutionLock:
    __slots__ = "islocked"

    def __init__(self):
        self.islocked = False

    def acquire(self):
        if not self.islocked:
            self.islocked = True
            return True
        return False


class CacheBase:
    __slots__ = "_cache", "_cache_popleft", "_cache_append", "_max_size"

    def __init__(self, max_size: int):
        self._cache = deque(maxlen=max_size)
        self._cache_popleft = self._cache.popleft
        self._cache_append = self._cache.append

        self._max_size = max_size


class LockCache(CacheBase):
    __slots__ = ()

    def put_back(self, lock: ExecutionLock):
        lock.islocked = False
        self._cache_append(lock)

    def get_or_create(self) -> ExecutionLock:
        return self._cache_popleft() if self._cache else ExecutionLock()


class EventCache(CacheBase):
    __slots__ = ()

    def put_back(self, event: Event):
        event.clear()
        self._cache_append(event)

    def get_or_create(self) -> Event:
        return self._cache_popleft() if self._cache else Event()


global_lock_cache = LockCache(1024)
global_event_cache = EventCache(1024)


class Aggregator:
    _func: Callable[[Any], Awaitable[Iterable]]
    _max_count: Optional[int]
    _leeway: float
    _first_call_at: Optional[float]
    _args: list
    _futures: List[Future]
    _event: Event
    _lock: ExecutionLock

    def __init__(
        self,
        func: Callable[[Any], Awaitable[Iterable]],
        *,
        timeout: float,
        leeway_ms: float,
        max_count: Optional[int] = None,
        loop: Optional[BaseEventLoop] = None,
    ):
        if max_count is not None and max_count <= 0:
            raise ValueError("max_count must be positive int or None")

        if leeway_ms <= 0:
            raise ValueError("leeway_ms must be positive float")

        self._func = func
        self._max_count = max_count
        self._leeway = leeway_ms / 1000
        self._timeout = timeout
        self.loop = loop or get_running_loop()

        self._clear()

    def _clear(self) -> None:
        self._first_call_at = None
        self._args = []
        self._futures = []
        self._event = global_event_cache.get_or_create()
        self._lock = global_lock_cache.get_or_create()

    async def _execute(
        self, *, args: list, futures: List[Future], timeout: float
    ) -> None:
        try:
            results = await self._func(args, timeout=timeout)
        except TimeoutError as exc:
            for future in filter(lambda fut: not fut.done(), futures):
                future.set_exception(exc)
        else:
            for future, result in zip(futures, results):
                if not future.done():
                    future.set_result(result)

    async def aggregate(self, arg: Any) -> Any:
        if self._first_call_at is None:
            self._first_call_at = monotonic()
        first_call_at = self._first_call_at

        args: list = self._args
        args.append(arg)

        futures: List[Future] = self._futures
        future = Future()
        futures.append(future)

        event: Event = self._event
        lock: ExecutionLock = self._lock

        if len(args) == self._max_count:
            event.set()
            self._clear()
        else:
            # Waiting for max_count requests or a timeout
            try:
                await wait_for(
                    event.wait(),
                    timeout=first_call_at + self._leeway - monotonic(),
                )
            except TimeoutError:
                func = self._func
                if isinstance(func, FunctionType):
                    func_name = func.__name__
                elif isinstance(func, partial):
                    func_name = func.func.__name__
                else:
                    func_name = str(func)

                log.debug(
                    "Aggregation timeout of %s for batch started at %.4f "
                    "with %d calls after %.2f ms",
                    func_name,
                    first_call_at,
                    len(futures),
                    (self.loop.time() - first_call_at) * 1000,
                )

        if args is self._args:  # timeout but no max_count
            self._clear()

        if lock.acquire():  # collect a batch here
            await self._execute(
                args=args,
                futures=futures,
                timeout=first_call_at + self._timeout - monotonic(),
            )
            global_lock_cache.put_back(lock)
            global_event_cache.put_back(event)

        return await future


class AsyncAggregator(Aggregator):
    async def _execute(
        self, *, args: list, futures: List[Future], timeout: float
    ) -> None:
        await self._func(args, futures, timeout=timeout)
