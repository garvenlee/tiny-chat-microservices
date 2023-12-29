from hashlib import md5
from logging import getLogger
from dataclasses import dataclass
from typing import Callable, Awaitable

from asyncio import get_running_loop
from blacksheep.messages import Request, Response
from blacksheep.server.application import Application
from blacksheep.server.responses import json
from cachetools import LRUCache

# from rpc.redis_service import RedisService
# from chatp.manager import GrpcClientManager
from chatp.redis.client import RedisClient
from chatp.redis.model import *


logger = getLogger("AllowOrDenyMiddleware")
logger.setLevel(10)


@dataclass
class IPHashKey:
    md5_key: str

    @property
    def redis_blocked_key(self):
        return f"chatp:redis:ratelimiter:ip:blocked:{self.md5_key}"


class AllowOrDenyMiddleware:
    def __init__(
        self,
        redis_client: RedisClient,
        # grpc_manager: GrpcClientManager,
        app: Application,
    ):
        self.app = app
        self.redis_client = redis_client
        self.ip_key_cache = LRUCache(maxsize=2**14)  # nearly 200MB
        # self.service_getter: Callable[[], RedisService] = partial(
        #     grpc_manager.get, "RedisService"
        # )
        # self.service: RedisService = service

    async def __call__(
        self, request: Request, handler: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        scope = request.scope

        ip = request.client_ip
        cache = self.ip_key_cache
        if (cacheline := cache.get(ip)) is None:
            scope["ip_key"] = hash_key = await get_running_loop().run_in_executor(
                None,
                lambda: md5(ip.encode(), usedforsecurity=True).hexdigest(),
            )
            cache[ip] = cacheline = IPHashKey(hash_key)
        else:
            scope["ip_key"] = cacheline.md5_key  # ratelimiter may use this key

        # redis_client: RedisClient = self.app.service_provider[RedisClient]
        value, status = await self.redis_client.redis_get(
            key=cacheline.redis_blocked_key
        )
        if status is REDIS_SUCCESS:
            if value == "":
                logger.info(f"{ip} request {scope['path']}")
                return await handler(request)
            else:
                logger.warning(f"{ip} reqests too many times, needs blocked")
                return json(
                    {
                        "info": "Blocked",
                        "retry_after": 3600,  # TODO accurately give this value
                    },
                    status=403,
                )
        elif status is REDIS_TIMEOUT:
            return json(
                {
                    "info": "Gateway timeout",
                    "retry_after": 2.5,
                },
                status=504,
            )
        else:
            return json(
                {
                    "info": "Busy Now",
                    "retry_after": 5,  # TODO accurately give this value
                },
                status=502,
            )
