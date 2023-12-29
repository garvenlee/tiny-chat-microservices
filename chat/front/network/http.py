from logging import getLogger
from typing import Union, Optional
from enum import IntEnum
from httpx import (
    Response as HttpxResponse,
    AsyncClient,
    Timeout,
    Limits,
    TimeoutException,
    NetworkError,
)

from utils.context import appid


logger = getLogger("http-connection")


class HttpStatus(IntEnum):
    Success = 0
    Failed = 1
    Timeout = 2
    NotFound = 3
    Forbidden = 4


SUCCESS = HttpStatus.Success
FAILED = HttpStatus.Failed
TIMEOUT = HttpStatus.Timeout
NOT_FOUND = HttpStatus.NotFound
FORBIDDEN = HttpStatus.Forbidden

status_map = {
    200: SUCCESS,
    202: FAILED,
    400: FAILED,
    403: FORBIDDEN,
    404: NOT_FOUND,
    503: FAILED,
    504: TIMEOUT,
}

exception_message = "http-request {exc_type}: {meth_name}, detailed_info: {exc_val}"

# TODO retry mechanism


class DummyResponse:
    __slots__ = "status_code"

    def __init__(self, status_code: int):
        self.status_code = status_code


class HttpConnection:
    __touched__ = (
        "login",
        "register",
        "query_user",
        "add_friend",
        "confirm_friend",
        "reject_friend",
        "get_friend_list",
        "get_chat_list",
    )

    def __init__(
        self,
        host: str,
        port: int,
    ):
        self._host, self._port = host, port

        self._client = AsyncClient(
            timeout=Timeout(connect=5, read=60, write=10, pool=5),
            limits=Limits(
                max_connections=5,
                max_keepalive_connections=2,
                keepalive_expiry=10,
            ),
        )

    async def login(
        self, email: str, password: str
    ) -> Union[HttpxResponse, DummyResponse]:
        try:
            return await self._client.post(
                url=f"http://{self._host}:{self._port}/user/login",
                data={"email": email, "password": password},
                timeout=5,
            )
        except TimeoutException as exc:
            logger.debug(
                exception_message.format(
                    meth_name="login", exc_type="timeout", exc_val=exc
                )
            )
            return DummyResponse(status_code=504)
        except NetworkError as exc:
            logger.debug(
                exception_message.format(
                    meth_name="login", exc_type="failed", exc_val=exc
                )
            )
            return DummyResponse(status_code=503)

    async def register(
        self, email: str, password: str, username: str
    ) -> Union[HttpxResponse, DummyResponse]:
        try:
            return await self._client.post(
                url=f"http://{self._host}:{self._port}/user/register",
                data={
                    "email": email,
                    "password": password,
                    "username": username,
                    "appid": appid,
                },
                timeout=5,
            )
        except TimeoutException as exc:
            logger.debug(
                exception_message.format(
                    meth_name="register", exc_tp="timeout", exc_val=exc
                )
            )
            return DummyResponse(status_code=504)
        except NetworkError as exc:
            logger.debug(
                exception_message.format(
                    meth_name="register", exc_tp="failed", exc_val=exc
                )
            )
            return DummyResponse(status_code=503)

    async def refresh(
        self, uid: int, refresh_token: str
    ) -> Union[HttpxResponse, DummyResponse]:
        try:
            return await self._client.post(
                url=f"http://{self._host}:{self._port}/user/refresh_token",
                data={
                    "uid": uid,
                    "refresh_token": refresh_token,
                },
                timeout=5,
            )
        except TimeoutException as exc:
            logger.debug(
                exception_message.format(
                    meth_name="refresh", exc_tp="timeout", exc_val=exc
                )
            )
            return DummyResponse(status_code=504)
        except NetworkError as exc:
            logger.debug(
                exception_message.format(
                    meth_name="refresh", exc_tp="failed", exc_val=exc
                )
            )
            return DummyResponse(status_code=503)

    async def query_user(
        self, email: str, access_token: str
    ) -> Union[HttpxResponse, DummyResponse]:
        try:
            return await self._client.post(
                url=f"http://{self._host}:{self._port}/user/query_user",
                data={"email": email},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=5,
            )
        except TimeoutException as exc:
            logger.debug(
                exception_message.format(
                    meth_name="query_user", exc_tp="timeout", exc_val=exc
                )
            )
            return DummyResponse(status_code=504)
        except NetworkError as exc:
            logger.debug(
                exception_message.format(
                    meth_name="query_user", exc_tp="failed", exc_val=exc
                )
            )
            return DummyResponse(status_code=503)

    async def add_friend(
        self,
        address_id: int,
        request_uid: str,
        request_email: str,
        request_username: str,
        access_token: str,
        request_message: Optional[str] = None,
    ) -> Union[HttpxResponse, DummyResponse]:
        try:
            data = {
                "address_id": address_id,
                "request_uid": request_uid,
                "request_email": request_email,
                "request_username": request_username,
                "appid": appid,
            }
            if request_message is not None:
                data["request_msg"] = request_message

            return await self._client.post(
                url=f"http://{self._host}:{self._port}/friend/friend_request",
                data=data,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=5,
            )
        except TimeoutException as exc:
            logger.debug(
                exception_message.format(
                    meth_name="add_friend", exc_tp="timeout", exc_val=exc
                )
            )
            return DummyResponse(status_code=504)
        except NetworkError as exc:
            logger.debug(
                exception_message.format(
                    meth_name="add_friend", exc_tp="failed", exc_val=exc
                )
            )
            return DummyResponse(status_code=503)

    def _friend_confirm_helper(action: int, name: str):
        async def inner_impl(
            self: "HttpConnection", uid: int, access_token: str
        ) -> Union[HttpxResponse, DummyResponse]:
            try:
                return await self._client.post(
                    url=f"http://{self._host}:{self._port}/friend/friend_confirm",
                    data={"address_id": uid, "action": action, "appid": appid},
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=5,
                )
            except TimeoutException as exc:
                logger.debug(
                    exception_message.format(
                        meth_name="confirm_friend", exc_tp="timeout", exc_val=exc
                    )
                )
                return DummyResponse(status_code=504)
            except NetworkError as exc:
                logger.debug(
                    exception_message.format(
                        meth_name="confirm_friend", exc_tp="failed", exc_val=exc
                    )
                )
                return DummyResponse(status_code=503)

        inner_impl.__name__ = name
        inner_impl.__qualname__ = f"HttpConnection.{name}"
        return inner_impl

    confirm_friend = _friend_confirm_helper(action=0, name="confirm_friend")
    reject_friend = _friend_confirm_helper(action=1, name="reject_friend")

    async def pull_inbox(self, last_max_msg_id: int, access_token: str):
        try:
            return await self._client.post(
                url=f"http://{self._host}:{self._port}/chat/pull_inbox",
                data={"last_max_msg_id": last_max_msg_id},
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
        except TimeoutException as exc:
            logger.debug(
                exception_message.format(
                    meth_name="pull_inbox", exc_tp="timeout", exc_val=exc
                )
            )
            return DummyResponse(status_code=504)
        except NetworkError as exc:
            logger.debug(
                exception_message.format(
                    meth_name="pull_inbox", exc_tp="failed", exc_val=exc
                )
            )
            return DummyResponse(status_code=503)

    async def pull_sessions(
        self, session_ids: list[int], access_token: str, *, timeout: float = 60
    ):
        async with self._client.stream(
            "POST",
            f"http://{self._host}:{self._port}/chat/pull_sessions",
            json={"session_ids": session_ids},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
        ) as response:
            async for chunk in response.aiter_bytes():
                yield chunk

    async def get_chat_list(
        self, access_token: str
    ) -> Union[HttpxResponse, DummyResponse]:
        try:
            return await self._client.get(
                url=f"http://{self._host}:{self._port}/chat/chat_list",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
        except TimeoutException as exc:
            logger.debug(
                exception_message.format(
                    meth_name="get_chat_list", exc_tp="timeout", exc_val=exc
                )
            )
            return DummyResponse(status_code=504)
        except NetworkError as exc:
            logger.debug(
                exception_message.format(
                    meth_name="get_chat_list", exc_tp="failed", exc_val=exc
                )
            )
            return DummyResponse(status_code=503)

    async def get_friend_list(
        self, access_token: str
    ) -> Union[HttpxResponse, DummyResponse]:
        try:
            return await self._client.get(
                url=f"http://{self._host}:{self._port}/friend/friend_list",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
        except TimeoutException as exc:
            logger.debug(
                exception_message.format(
                    meth_name="get_friend_list", exc_tp="timeout", exc_val=exc
                )
            )
            return DummyResponse(status_code=504)
        except NetworkError as exc:
            logger.debug(
                exception_message.format(
                    meth_name="get_friend_list", exc_tp="failed", exc_val=exc
                )
            )
            return DummyResponse(status_code=503)
