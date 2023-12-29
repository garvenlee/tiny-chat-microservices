from functools import partial
from typing import Any, Callable, Coroutine, Optional

from asyncio import TimeoutError as AsyncIOTimeoutError

from .model import *
from .cache_service import RedisCacheService
from ..utils.aggregator import Aggregator, AsyncAggregator

REDIS_URI: str = "redis://@127.0.0.1:6379/0"
REDIS_POOL_MAX_SIZE = 5


class RedisClient:
    def __init__(
        self, uri: Optional[str] = None, max_connections: Optional[int] = None
    ):
        self.engine = engine = RedisCacheService(
            uri=uri or REDIS_URI,
            max_connections=max_connections or REDIS_POOL_MAX_SIZE,
        )

        self._groups = {}

        self.redis_read = engine.redis_read
        self.redis_write = engine.redis_write

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        engine, self.engine = self.engine, None
        await engine.__aexit__(exc_tp, exc_val, exc_tb)

        self._groups = None

    async def __aenter__(self):
        engine = self.engine
        await engine.__aenter__()

        redis_read_batch = engine.redis_read_batch
        redis_write_batch = engine.redis_write_batch

        groups = self._groups
        for task_type in (
            TASK_GET,
            TASK_SET,
            TASK_DELETE,
            TASK_LPUSH,
            TASK_RPUSH,
        ):
            if task_type & 1:  # OPERATION_WRITE
                groups[task_type] = AsyncAggregator(
                    partial(redis_write_batch, task_type),
                    timeout=5,
                    leeway_ms=5,
                    max_count=25,
                ).aggregate

            else:
                groups[task_type] = Aggregator(
                    partial(redis_read_batch, task_type),
                    timeout=3,
                    leeway_ms=5,
                    max_count=50,
                ).aggregate
        return self

    def register(self, key: Any, handler: Callable[[Any], Coroutine[None, None, Any]]):
        self._groups[key] = handler

    async def dispatch(self, key: Any, *arg: Any):
        return await self._groups[key](arg)

    async def redis_get(self, key) -> tuple[str, ResponseStatus]:
        try:
            data = await self._groups[TASK_GET]((key,))
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def redis_set(self, key, value) -> tuple[bool, ResponseStatus]:
        try:
            data = await self._groups[TASK_SET]((key, value))
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def redis_setnx(self, key, value, *, timeout: float):
        try:
            data = await self.redis_write(TASK_SETNX, (key, value), timeout=timeout)
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def redis_mget(
        self, *keys, timeout: float
    ) -> tuple[tuple[str], ResponseStatus]:
        try:
            data = await self.redis_read(TASK_MGET, keys, timeout=timeout)
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def redis_mset(
        self, mapping: dict, *, timeout: float
    ) -> tuple[bool, ResponseStatus]:
        try:
            data = await self.redis_write(TASK_MSET, (mapping,), timeout=timeout)
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def redis_hlen(self, key, *, timeout: float):
        try:
            data = await self.redis_read(TASK_HLEN, (key,), timeout=timeout)
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def redis_hget(
        self, key, field, *, timeout: float
    ) -> tuple[str, ResponseStatus]:
        try:
            data = await self.redis_read(TASK_HGET, (key, field), timeout=timeout)
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def redis_hset(
        self, key, field, value, *, timeout: float
    ) -> tuple[bool, ResponseStatus]:
        try:
            data = await self.redis_write(
                TASK_HSET, (key, field, value), timeout=timeout
            )
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def redis_hgetall(
        self, key, *, timeout: float
    ) -> tuple[dict, ResponseStatus]:
        try:
            data = await self.redis_read(TASK_HGETALL, (key,), timeout=timeout)
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def redis_hdel(
        self, key, *fields, timeout: float
    ) -> tuple[bool, ResponseStatus]:
        try:
            data = await self.redis_write(TASK_HDEL, (key, *fields), timeout=timeout)
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def redis_delete(self, key) -> tuple[bool, ResponseStatus]:
        try:
            data = await self._groups[TASK_DELETE]((key,))
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def redis_incr(
        self, key, increment: int = 1, *, timeout: int | float = 1
    ) -> tuple[int, ResponseStatus]:
        try:
            data = await self.redis_write(TASK_INCR, (key, increment), timeout=timeout)
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def redis_lpush(self, key, *values) -> tuple[bool, ResponseStatus]:
        try:
            data = await self._groups[TASK_LPUSH]((key, *values))
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def redis_rpush(self, key, *values) -> tuple[bool, ResponseStatus]:
        try:
            data = await self._groups[TASK_RPUSH]((key, *values))
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def ip_ratelimiter(
        self, keys, argv, *, timeout: float
    ) -> tuple[RatelimiterStatus, ResponseStatus]:
        try:
            data = await self.redis_read(TASK_IP_LIMITER, (keys, argv), timeout=timeout)
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED

    async def token_ratelimiter(
        self, keys, argv, *, timeout: float
    ) -> tuple[RatelimiterStatus, ResponseStatus]:
        try:
            data = await self.redis_read(
                TASK_TOKEN_LIMITER, (keys, argv), timeout=timeout
            )
        except AsyncIOTimeoutError:
            return None, REDIS_TIMEOUT
        else:
            return data, REDIS_SUCCESS if data is not None else REDIS_FAILED
