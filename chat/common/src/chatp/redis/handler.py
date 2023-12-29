from logging import getLogger
from time import time
from typing import Union, Iterable
from packaging.version import Version

from redis.asyncio import Redis as AsyncRedis
from redis.asyncio.retry import Retry
from redis.backoff import EqualJitterBackoff
from redis.exceptions import ConnectionError, BusyLoadingError

from .model import *

logger = getLogger("RedisService")
# current_path = os.path.abspath(__file__)
# dir_name = os.path.dirname(current_path)
# with open(
#     f"{dir_name}/microservices/redis/utils/lua/library.lua", "r", encoding="utf-8"
# ) as fs:
#     LIBRARY = fs.read()

# with open(f"./lua/library.lua", "r", encoding="utf-8") as fs:
#     LIBRARY = fs.read()


IP_RATELIMITER = """
        local key = "chatp:redis:ratelimiter:ip:" .. KEYS[1]
        local current_ms = tonumber(ARGV[1])
        local sliding_window = tonumber(ARGV[2])

        local window_start_ms = current_ms - sliding_window * 1000
        local window_count = redis.call("zcount", key, window_start_ms, current_ms)
        if tonumber(window_count) >= 1 then
            return 1 
        end

        redis.call("zadd", key, current_ms, ARGV[1])
        local trace_cycle = tonumber(ARGV[3])
        local trace_threshold = tonumber(ARGV[4])
        
        local trace_window_start_ms = current_ms - trace_cycle * 1000
        local trace_window_count = redis.call("zcount", key, trace_window_start_ms, current_ms)
        if trace_window_count > trace_threshold then
            local blocked_time = tonumber(ARGV[5])
            redis.call("set", "chatp:redis:ratelimiter:ip:blocked:" .. KEYS[1], 1, "nx" ,"ex", blocked_time)
            return 2
        end

        if trace_window_count == 1 then
            redis.call("expire", key, trace_cycle)
        end
        return 0
    """

TOKEN_RATELIMITER = """
        local object_tag = KEYS[1]
        local field_prefix = "chatp:redis:ratelimiter:token:"
        local token_key = field_prefix .. "capacity:" .. object_tag
        local last_refreshed_key = field_prefix .. "last_refreshed:" .. object_tag

        local current_ms = tonumber(ARGV[1])
        local prefetch = tonumber(ARGV[2])
        local inflow_window = tonumber(ARGV[3]) * 1000
        local capacity = tonumber(ARGV[4])
        local rate = tonumber(ARGV[5])

        local tokens = redis.call("get", token_key)
        local leftover
        if tokens then
            leftover = tonumber(tokens)
            if prefetch > leftover then
                local last_refreshed = tonumber(redis.call("get", last_refreshed_key))
                local time_passed = math.max(current_ms - last_refreshed, 0)

                if time_passed >= inflow_window then
                    local new_tokens = math.floor(time_passed * rate)
                    leftover = math.min(leftover + new_tokens, capacity)

                    redis.call("set", token_key, leftover)
                    redis.call("set", last_refreshed_key, current_ms)

                    if prefetch > leftover then
                        return 1
                    end
                else
                    return 1
                end
            end    
        else
            leftover = capacity
            redis.call("set", token_key, capacity)
            redis.call("set", last_refreshed_key, current_ms)

            -- just in order to defend faulted use
            if prefetch > leftover then
                return 1
            end
        end

        if prefetch == 1 then
            redis.call("decr", token_key)
        else
            redis.call("decrby", token_key, prefetch)
        end
        return 0
    """


class RedisHandlerMixin:
    @staticmethod
    def register_script(redis_client: AsyncRedis, script: str):
        return redis_client.register_script(script)

    @staticmethod
    async def validate_version(redis_client: AsyncRedis):
        info = await redis_client.info()
        version = info["redis_version"]
        if Version(version) < Version("7.0"):
            raise RuntimeError(
                f"Redis 7.0 is the minimum version supported. The server reported version {version!r}."
            )

    # @staticmethod
    # async def register_library(redis_client: AsyncRedis):
    #     if not await redis_client.function_list("RTQ"):
    #         await redis_client.function_load(LIBRARY, replace=True)

    # async def ip_ratelimiter(self, keys: Sequence[KeysT], argv: Sequence[EncodableT]):
    #     return await self.ip_ratelimiter(keys, argv)

    # async def token_ratelimiter(
    #     self, keys: Sequence[KeysT], argv: Sequence[EncodableT]
    # ):
    #     return await self.token_ratelimiter(keys, argv)

    async def handler_initialize(self, uri: str, total_connections: int):
        backend: AsyncRedis = AsyncRedis.from_url(
            url=uri,
            max_connections=total_connections,
            socket_timeout=1,  # used in `read_response`
            socket_connect_timeout=5,  # used in `connect`
            # retry_on_timeout=True,
            retry=Retry(
                EqualJitterBackoff(base=0.02),  # 20ms
                3,
                supported_errors=(ConnectionError, BusyLoadingError),
            ),
        )

        # ratelimiter script
        self.ip_ratelimiter = self.register_script(backend, IP_RATELIMITER)
        self.token_ratelimiter = self.register_script(backend, TOKEN_RATELIMITER)
        self.ip_limiter_responses = (
            RATE_ALLOWED,
            RATE_REJECTED,
            RATE_BLOCKED,
        )
        self.token_limiter_responses = (RATE_ALLOWED, RATE_BLOCKED)

        # Redis Throttled Queue
        # await self.validate_version(backend)
        # await self.register_library(backend)

        self._backend = backend
        for meth in [
            "set",
            "setnx",
            "get",
            "mset",
            "mget",
            "hlen",
            "hset",
            "hdel",
            "hget",
            "hgetall",
            "lpush",
            "rpush",
            "delete",
            "incr",
            "decr",
        ]:
            setattr(self, meth, getattr(backend, meth))

        self._handlers = {
            TASK_BATCH_SET: (self.redis_batch_set, self.redis_batch_set_rollback),
            TASK_BATCH_GET: (self.redis_batch_get, None),
            TASK_BATCH_DELETE: (self.redis_batch_delete, None),
            TASK_GET: (self.redis_get, None),
            TASK_MGET: (self.redis_mget, None),
            TASK_HGET: (self.redis_hget, None),
            TASK_SET: (self.set, self.redis_set_rollback),
            TASK_SETNX: (self.setnx, None),
            TASK_MSET: (self.mset, self.redis_mset_rollback),
            TASK_HSET: (self.hset, self.redis_hset_rollback),
            TASK_HLEN: (self.hlen, None),
            TASK_HDEL: (self.hdel, None),
            TASK_HGETALL: (self.hgetall, None),
            TASK_INCR: (self.incr, self.redis_incr_rollback),
            TASK_LPUSH: (self.lpush, None),
            TASK_RPUSH: (self.rpush, None),
            TASK_DELETE: (self.delete, None),
            # TASK_UNLINK: (self.redis_unlink, None),
            TASK_IP_LIMITER: (self.redis_ip_ratelimiter, None),
            TASK_TOKEN_LIMITER: (self.redis_token_ratelimiter, None),
        }

    # TODO detailed optimize: rollback

    async def redis_get(self, key) -> str:
        return await self.get(key) or ""

    async def redis_mget(self, items: Iterable) -> list[str]:
        # self._backend.mget(request.keys)
        results = await self.mget(*tuple(items))
        return [val if val is not None else "" for val in results]

    async def redis_hget(self, key, field) -> str:
        return await self.hget(key, field) or ""

    async def redis_batch_get(self, *items: tuple) -> list[str]:
        results = await self.mget(*tuple(item[0] for item in items))
        return [val if val is not None else "" for val in results]

    async def redis_batch_set(self, *items: tuple) -> bool:
        # self._backend.mset()
        return await self.mset(dict(items))

    async def redis_batch_delete(self, *items: tuple) -> bool:
        return await self.delete(*tuple(item[0] for item in items))

    async def redis_set_rollback(self, key, _) -> bool:
        return await self.delete(key)

    async def redis_mset_rollback(self, mapping: dict):
        # self._backend.delete()
        return await self.delete(*tuple(mapping.keys()))

    async def redis_hset_rollback(self, key, field, __):
        return await self.hdel(key, field)

    async def redis_batch_set_rollback(self, *items: tuple):
        # self._backend.delete()
        return await self.delete(*tuple(item[0] for item in items))

    # async def redis_unlink(self, request: RedisDeleteRequest):
    #     return await self.unlink(request.key)

    async def redis_incr(self, key: str, increment: int = 1):
        return await self.incr(key, increment)

    async def redis_incr_rollback(self, key: str, increment: int):
        return await self.decr(key, increment)

    async def redis_ip_ratelimiter(
        self,
        keys,
        argv,
    ) -> RatelimiterStatus:
        response = await self.ip_ratelimiter(keys, argv)
        return self.ip_limiter_responses[response]

    async def redis_token_ratelimiter(
        self,
        keys,
        argv,
    ) -> RatelimiterStatus:
        response = await self.token_ratelimiter(keys, argv)
        return self.token_limiter_responses[response]

    # Throttled Queue
    async def size(self, count_key: str):
        return int(await self._backend.get(count_key) or 0)

    async def push(
        self, name: str, data: Union[str, bytes], *, prefix: str, priority: int = 0
    ):
        if ":" in name:
            raise ValueError('Incorrect value for `key`. Cannot contain ":".')
        return await self._backend.fcall("RTQ_PUSH", 0, prefix, name, priority, data)

    async def pop(
        self,
        prefix: str,
        limit: int = 5,
        resolution: int = 1,  # 1s
        window: Union[str, bytes, int] = Ellipsis,
    ) -> Union[str, bytes, None]:
        if window is Ellipsis:
            window = int(time()) // resolution % 60
        value = await self._backend.fcall(
            "RTQ_POP", 0, prefix, window, limit, resolution
        )
        return value

    async def cleanup(self, prefix: str):
        return await self._backend.fcall("RTQ_CLEANUP", 0, prefix)
