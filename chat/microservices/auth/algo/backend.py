from jwt.exceptions import (
    InvalidSignatureError,
    ImmatureSignatureError,
    InvalidTokenError,
)
import asyncio
from calendar import timegm
from typing import Optional, Tuple
from datetime import datetime, timezone

from .config import Configuraton
from .authentication import AuthHandler
from .model import AuthStatus


class AuthBackend:
    def __init__(self, config: Configuraton, loop: asyncio.BaseEventLoop) -> None:
        self.handler = AuthHandler(config)
        self._loop = loop

    def generate_token(self, uid: int):
        handler = self.handler
        access_token = handler.generate_access_token(uid)
        refresh_token = handler.generate_refresh_token()
        return access_token, refresh_token

    async def post_authenticate(self, uid: int) -> Optional[tuple[str, str]]:
        access_token, refresh_token = await self._loop.run_in_executor(
            None, self.generate_token, uid
        )
        result = await self.handler.store_refresh_token(
            uid=uid,
            refresh_token=refresh_token,
        )
        if not result:
            return
        return access_token, refresh_token

    async def authenticate(self, access_token: str) -> Tuple["AuthStatus", int]:
        handler = self.handler
        try:
            payload = await self._loop.run_in_executor(
                None, handler._decode, access_token
            )
        except (ImmatureSignatureError, InvalidSignatureError):
            return AuthStatus.InvalidSignature, 0
        except InvalidTokenError:
            return AuthStatus.InvalidToken, 0
        except BaseException:
            return AuthStatus.InvalidPayload, 0
        else:
            # must have exp and user_id
            if not handler.is_payload_valid(payload):
                return AuthStatus.InvalidPayload, 0

            now = timegm(datetime.now(tz=timezone.utc).utctimetuple())
            exp = int(payload["exp"])

            config = handler.config
            return AuthStatus.Success if exp > (
                now - config.LEEWAY
            ) else AuthStatus.Expired, int(payload[config.USER_ID])

    async def refresh(
        self, uid: int, user_refresh_token: str
    ) -> Optional[Tuple[str, str]]:
        handler = self.handler
        redis_refresh_token: Optional[str] = await handler.retrieve_refresh_token(uid)
        if redis_refresh_token != user_refresh_token:
            return

        access_token, refresh_token = await self._loop.run_in_executor(
            None, self.generate_token, uid
        )
        result = await handler.store_refresh_token(
            uid=uid,
            refresh_token=refresh_token,
        )
        if not result:
            return
        return access_token, refresh_token
