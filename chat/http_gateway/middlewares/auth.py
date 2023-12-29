from time import monotonic
from logging import getLogger
from functools import wraps, partial
from typing import Tuple, Callable, Union, Awaitable, Optional

from python_digest import (
    build_digest_challenge,
    parse_digest_credentials,
    validate_nonce,
    calculate_request_digest,
    calculate_partial_digest,
    DigestResponse,
)
from asyncio import get_running_loop
from blacksheep.messages import Request, Response
from blacksheep.server.application import Application
from blacksheep.server.responses import json, text

from rpc.auth_service import AuthService
from chatp.proto.services.auth.auth_user_pb2 import (
    AUTH_SUCCESS,
    AUTH_EXPIRED,
    AUTH_TIMEOUT,
    AuthTokenReply,
    AuthRefreshTokenReply,
)

# from concurrent.futures import ThreadPoolExecutor

from chatp.manager.grpc_client import GrpcClientManager
from chatp.rpc.model import CallResult, GRPC_SUCCESS, GRPC_TIMEOUT


logger = getLogger("AuthMiddleware")
logger.setLevel(10)


def digest_response(field: str, secret: str) -> Optional[DigestResponse]:
    try:
        resp: DigestResponse = parse_digest_credentials(field)
        if validate_nonce(resp.nonce, secret):
            expected_response = calculate_request_digest(
                "GET",
                calculate_partial_digest(resp.username, resp.realm, "121380316"),
                resp,
            )
        else:
            return False
    except Exception as exc:
        logger.warning(exc.args[0])
        return False
    else:
        return expected_response == resp.response


class AuthenticationError(Exception):
    pass


class HttpAuthentication:
    SECRET = "anything 0x"
    REALM = "@chatApp.com"
    OPAQUE = "ADAC33GJHGGYTADYAYD"

    def __init__(self, grpc_manager: GrpcClientManager, app: Application):
        self.app = app
        self.service_getter = partial(grpc_manager.find_service, "AuthService")
        # self.service: AuthService = service

    async def authenticate_token(
        self, request: Request
    ) -> Union[int, Tuple[int, str, str]]:
        service: AuthService = self.service_getter()

        field: bytes = request.headers.get_first(b"Authorization")
        if field is None:
            info = "missing access_token"
            logger.warning(info)
            raise AuthenticationError(400, info)  # Bad Request
        else:
            if not field.startswith(b"Bearer "):
                info = "invalid Authorization"
                logger.warning(info)
                raise AuthenticationError(400, info)
            else:
                token = field[7:]

        result: CallResult = await service.AuthToken(
            access_token=token.decode("utf-8"), timeout=3
        )

        if (grpc_status := result.status) is GRPC_SUCCESS:
            reply: AuthTokenReply = result.data
            uid = reply.uid

            if (status := reply.status) is AUTH_SUCCESS:
                logger.info("user successfully authenticated")
                return uid
            elif status is AUTH_EXPIRED:
                logger.warning("user's token is expired, needs refresh")
                refresh_token = request.headers.get_first(b"refresh_token")
                if refresh_token is None:
                    info = "missing refresh_token"
                    logger.warning(info)
                    raise AuthenticationError(400, info)  # Bad Request: needs refresh

                result: CallResult = await service.AuthRefresh(
                    refresh_token=refresh_token.decode("utf-8"), uid=uid, timeout=3
                )

                if (grpc_status := result.status) is GRPC_SUCCESS:
                    data: AuthRefreshTokenReply = result.data
                    if (status := data.status) is AUTH_SUCCESS:
                        logger.info("user successfully authenticated")
                        # new tokens
                        return uid, data.access_token, data.refresh_token
                    elif status is AUTH_TIMEOUT:
                        info = "user service timeout"
                        logger.warning(info)
                        raise AuthenticationError(504, info)  # Gateway Timeout
                    else:  # failed, client must login again
                        info = "invalid token"
                        logger.warning(info)
                        raise AuthenticationError(401, info)  # Unauthorized
                elif grpc_status is GRPC_TIMEOUT:
                    info = "auth service is busy"
                    logger.warning(info)
                    raise AuthenticationError(504, info)  # Gateway Timeout
                else:
                    logger.warning(f"unknown error, {result.info}")
                    raise AuthenticationError(400, "invalid request")  # Bad Request

            elif status is AUTH_TIMEOUT:
                info = "user service timeout"
                logger.warning(info)
                raise AuthenticationError(504, info)  # Gateway Timeout
            else:  # failed, client must login again
                info = "invalid token"
                logger.warning(info)
                raise AuthenticationError(401, info)  # Unauthorized
        elif grpc_status is GRPC_TIMEOUT:
            info = "auth service is busy"
            logger.warning(info)
            raise AuthenticationError(504, info)  # Gateway Timeout
        else:
            logger.warning(f"unknown error, {result.info}")
            raise AuthenticationError(400, "invalid request")  # Bad Request

    def auth_token(self, handler: Callable[[Request], Awaitable[Response]]):
        @wraps(handler)
        async def inner(request: Request, *args, **kwargs):
            scope = request.scope
            try:
                data = await self.authenticate_token(request)
            except AuthenticationError as exc:
                err_code, err_msg = exc.args
                response = json({"info": err_msg}, status=err_code)
            else:
                if isinstance(data, tuple):
                    uid, access_token, refresh_token = data
                    scope["uid"] = uid  # inject uid
                    response = await handler(request, *args, **kwargs)

                    response.headers.add_many(
                        [
                            (b"access_token", access_token.encode("utf-8")),
                            (b"refresh_token", refresh_token.encode("utf-8")),
                        ]
                    )
                else:
                    uid = data
                    scope["uid"] = uid  # inject uid
                    response = await handler(request, *args, **kwargs)
            return response

        return inner

    def auth_metrics(self, handler: Callable[[Request], Awaitable[Response]]):
        self_cls = self.__class__
        digest_challenge = partial(
            build_digest_challenge,
            secret=self_cls.SECRET,
            realm=self_cls.REALM,
            opaque=self_cls.OPAQUE,
            stale=False,
        )
        secret = self_cls.SECRET

        @wraps(handler)
        async def inner(request: Request, *args, **kwargs):
            loop = get_running_loop()

            auth = request.headers.get_first(b"Authorization")
            if auth is None:
                www_auth_challenge: str = await loop.run_in_executor(
                    None, digest_challenge, monotonic()
                )

                headers = [
                    (b"WWW-Authenticate", www_auth_challenge.encode("latin-1")),
                ]
                return Response(401, headers)
            else:
                # print(auth)
                if await loop.run_in_executor(
                    None, digest_response, auth.decode("latin-1"), secret
                ):
                    return await handler(request, *args, **kwargs)
                else:
                    return text("error request", 400)

        return inner
