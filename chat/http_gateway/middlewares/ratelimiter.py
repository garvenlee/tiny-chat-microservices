from time import monotonic
from functools import wraps
from typing import Callable, Awaitable

from blacksheep.messages import Request, Response
from blacksheep.server.application import Application
from blacksheep.server.responses import text, json

from chatp.redis.client import RedisClient
from chatp.redis.model import *


class RatelimitingMiddleware:
    def __init__(
        self,
        redis_client: RedisClient,
        app: Application,
    ):
        self.app = app  # remain, maybe other function
        self.redis_client = redis_client
        # self.service_getter = partial(grpc_manager.get, "RedisService")
        # self.service: RedisService = service

    def ip_limiter(
        self,
        handler: Callable[[Request], Awaitable[Response]],
        *,
        sliding_window: int = 3,  # one request per 3s
        trace_cycle: int = 30,
        trace_threshold: int = 6,  # >= 6 req during 30s
        blocked_time: int = 600,  # block 600s
    ):
        @wraps(handler)
        async def inner(request: Request, *args, **kwargs):
            # redis_client: RedisClient = self.app.service_provider[RedisClient]
            ip_key = request.scope["ip_key"]
            # TODO set grpc argv all int
            code, status = await self.redis_client.ip_ratelimiter(
                keys=[ip_key],
                argv=[
                    str(int(round(monotonic() * 1000))),
                    str(sliding_window),
                    str(trace_cycle),
                    str(trace_threshold),
                    str(blocked_time),
                ],
                timeout=5,
            )
            if status is REDIS_SUCCESS:
                if code is RATE_ALLOWED:
                    return await handler(request, *args, **kwargs)
                elif code is RATE_REJECTED:
                    return json(
                        {
                            "info": "Too Many Requests",
                            "retry_after": sliding_window,
                        },
                        status=429,
                    )
                else:
                    return json(
                        {
                            "info": "Blocked",
                            "retry_after": 600,  # default 10min
                        },
                        status=403,
                    )
            elif status is REDIS_TIMEOUT:
                return text("Busy now", status=504)
            else:
                return text("Busy now", status=502)

        return inner

    # token ratelimiter
    def api_limiter(
        self,
        handler: Callable[[Request], Awaitable[Response]],
        prefix: str = None,
        prefetch: int = 1,  # maybe non-required
        inflow_window: int = 1,  # second
        capacity: int = 12,  # max tokens in inflow_window
        rate: int = 8,
    ):
        if prefix is None:
            prefix = handler.__name__

        @wraps(handler)
        async def inner(request: Request, *args, **kwargs):
            # redis_client: RedisClient = self.app.service_provider[RedisClient]

            code, status = await self.redis_client.token_ratelimiter(
                keys=[prefix],
                argv=[
                    str(int(round(monotonic() * 1000))),
                    str(prefetch),
                    str(inflow_window),
                    str(capacity),
                    str(rate),
                ],
                timeout=5,
            )

            if status is REDIS_SUCCESS:
                if code is RATE_ALLOWED:
                    return await handler(request, *args, **kwargs)
                else:  # rejected
                    return text("Blocked", status=403)
            elif status is REDIS_TIMEOUT:
                return text("Busy now", status=504)
            else:
                return text("Busy now", status=502)

        return inner
