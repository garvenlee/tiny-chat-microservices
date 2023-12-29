import time
import grpc
import asyncio
import logging

import base64
import secrets
from itsdangerous import URLSafeTimedSerializer as Serializer
from itsdangerous.exc import BadTimeSignature

from algo.backend import AuthBackend
from algo.model import AuthStatus
from chatp.proto.services.auth.auth_user_pb2 import (
    AUTH_SUCCESS,
    AUTH_TIMEOUT,
    AUTH_FAILED,
    AUTH_INCORRECT_EMAIL,
    AUTH_INCORRECT_PWD,
    AUTH_INCORRECT_CONFIRMATION,
    AUTH_ALREADY_EXISTS,
    AUTH_NOT_EXISTS,
    AUTH_EXPIRED,
    AUTH_UNKNOWN_ERROR,
    AuthLoginRequest,
    AuthLoginReply,
    AuthRegisterRequest,
    AuthRegisterReply,
    AuthRegisterConfirmRequest,
    AuthRegisterConfirmReply,
    AuthTokenRequest,
    AuthTokenReply,
    AuthRefreshTokenRequest,
    AuthRefreshTokenReply,
)
from chatp.proto.services.auth.auth_user_pb2_grpc import (
    AuthUserServicer as ProtoService,
)
from chatp.proto.services.user.user_pb2 import (
    USER_INCORRECT_EMAIL,
    USER_INCORRECT_PWD,
    USER_ALREADY_EXISTS,
    USER_NOT_EXISTS,
    USER_DB_TIMEOUT,
    USER_UNKNOWN_ERROR,
    UserLoginReply,
    UserRegisterReply,
    UserRegisterConfirmReply,
)

from chatp.manager.grpc_client import GrpcClientManager
from chatp.rpc.model import *


logger = logging.getLogger("AuthService")

DETAILED_INFO_MAP = {
    USER_INCORRECT_EMAIL: AUTH_INCORRECT_EMAIL,
    USER_INCORRECT_PWD: AUTH_INCORRECT_PWD,
    USER_ALREADY_EXISTS: AUTH_ALREADY_EXISTS,
    USER_NOT_EXISTS: AUTH_NOT_EXISTS,
    USER_DB_TIMEOUT: AUTH_TIMEOUT,
    USER_UNKNOWN_ERROR: AUTH_UNKNOWN_ERROR,
}


class AuthService(ProtoService):
    def __init__(
        self,
        grpc_manager: GrpcClientManager,
        backend: AuthBackend,
        loop: asyncio.BaseEventLoop,
    ) -> None:
        self.grpc_manager = grpc_manager
        self.service_getter = grpc_manager.find_service
        self.auth_backend = backend
        self._loop = loop
        self.state_initialize()

    def state_initialize(self):
        stamp = int(time.time())
        secret_keys = [
            base64.b64encode(secrets.token_bytes(12) + str(stamp % 1e4).encode("utf-8"))
            for _ in range(5)
        ]
        self.serializer = Serializer(secret_keys, b"chatApp salt")

    async def AuthLogin(
        self, request: AuthLoginRequest, context: grpc.aio.ServicerContext
    ) -> AuthLoginReply:
        start = time.monotonic()
        result: CallResult = await self.service_getter("UserService").UserLogin(
            email=request.email,
            password=request.password,
            timeout=context.time_remaining() - 1,  # reserve 1s for redis op
        )

        middle = time.monotonic()
        logger.warning(f"one login consumes: {middle-start}")

        if (grpc_status := result.status) is GRPC_SUCCESS:
            data: UserLoginReply = result.data
            if data.success:
                user = data.user
                # generate token and set redis
                if tokens := await self.auth_backend.post_authenticate(user.seq):
                    access_token, refresh_token = tokens
                    reply = AuthLoginReply(
                        status=AUTH_SUCCESS,
                        user=user,
                        access_token=access_token,
                        refresh_token=refresh_token,
                    )
                    logger.warning(
                        f"Token-process consumes: {time.monotonic() - middle}s."
                    )
                else:
                    # TODO maybe retry when RedisSet failed
                    logger.warning("Failed to store refersh token.")
                    reply = AuthLoginReply(status=AUTH_TIMEOUT)
            else:
                if (code := data.code) is USER_DB_TIMEOUT:
                    logger.warning("Found timeout in db query.")
                    reply = AuthLoginReply(status=AUTH_TIMEOUT)
                else:
                    reply = AuthLoginReply(
                        status=AUTH_FAILED, info=DETAILED_INFO_MAP[code]
                    )
        elif grpc_status is GRPC_TIMEOUT:
            logger.warning("Found timeout in GrpcCall<UserLogin>.")
            reply = AuthLoginReply(status=AUTH_TIMEOUT)
        else:
            logger.warning("Found unknown exception in GrpcCall<UserLogin>.")
            reply = AuthLoginReply(status=AUTH_FAILED, info=AUTH_UNKNOWN_ERROR)

        if not context.cancelled():
            return reply

    async def AuthRegister(
        self, request: AuthRegisterRequest, context: grpc.aio.ServicerContext
    ) -> AuthRegisterReply:
        result: CallResult = await self.service_getter("UserService").UserRegister(
            username=request.username,
            email=request.email,
            password=request.password,
            timeout=context.time_remaining(),
        )
        if (grpc_status := result.status) is GRPC_SUCCESS:
            data: UserRegisterReply = result.data
            if data.success:
                token = await self._loop.run_in_executor(
                    None,
                    self.serializer.dumps,
                    {"confirm": data.seq, "exp": time.monotonic() + 300},
                )
                reply = AuthRegisterReply(status=AUTH_SUCCESS, token=token)
            else:
                if (code := data.code) is USER_DB_TIMEOUT:
                    reply = AuthRegisterReply(status=AUTH_TIMEOUT)
                else:
                    reply = AuthRegisterReply(
                        status=AUTH_FAILED, info=DETAILED_INFO_MAP[code]
                    )
        elif grpc_status is GRPC_TIMEOUT:
            logger.warning("gateway countered timeout when user loged in")
            reply = AuthRegisterReply(status=AUTH_TIMEOUT)
        else:
            reply = AuthRegisterReply(status=AUTH_FAILED, info=AUTH_UNKNOWN_ERROR)

        if not context.cancelled():
            return reply

    async def AuthRegisterConfirm(
        self, request: AuthRegisterConfirmRequest, context: grpc.aio.ServicerContext
    ) -> AuthRegisterConfirmReply:
        token = request.token
        # TODO check expire and scratch uid from token
        try:
            info = await self._loop.run_in_executor(None, self.serializer.loads, token)
        except BadTimeSignature as exc:
            return AuthRegisterConfirmReply(status=AUTH_FAILED)
        else:
            # TODO check info data format
            if time.monotonic() - info["exp"] > 300:
                return AuthRegisterConfirmReply(
                    status=AUTH_EXPIRED, info=AUTH_INCORRECT_CONFIRMATION
                )

            result: CallResult = await self.service_getter(
                "UserService"
            ).UserRegisterConfirm(seq=info["confirm"], timeout=context.time_remaining())

            grpc_status = result.status
            if grpc_status is GRPC_SUCCESS:
                data: UserRegisterConfirmReply = result.data
                if data.success:
                    reply = AuthRegisterConfirmReply(status=AUTH_SUCCESS)
                elif data.code is USER_DB_TIMEOUT:
                    reply = AuthRegisterConfirmReply(status=AUTH_TIMEOUT)
                else:
                    reply = AuthRegisterConfirmReply(status=AUTH_FAILED)
            elif grpc_status is GRPC_TIMEOUT:
                logger.warning("gateway countered timeout when user loged in")
                reply = AuthRegisterConfirmReply(status=AUTH_TIMEOUT)
            else:
                reply = AuthRegisterConfirmReply(
                    status=AUTH_FAILED, info=AUTH_UNKNOWN_ERROR
                )

            if not context.cancelled():
                return reply

    async def AuthLogout(self, request, context: grpc.aio.ServicerContext):
        return super().AuthLogout(request, context)

    async def AuthToken(
        self, request: AuthTokenRequest, context: grpc.aio.ServicerContext
    ) -> AuthTokenReply:
        access_token: str = request.access_token
        status, uid = await self.auth_backend.authenticate(access_token)
        if status is AuthStatus.Success:
            return AuthTokenReply(status=AUTH_SUCCESS, uid=uid)
        elif status is AuthStatus.Expired:
            logger.info("user token has been expired")
            return AuthTokenReply(status=AUTH_EXPIRED, uid=uid)
        else:
            logger.warning(
                (
                    "invalid payload"
                    if status is AuthStatus.InvalidPayload
                    else "invalid signature"
                )
            )
            return AuthTokenReply(status=AUTH_FAILED)

    async def AuthRefresh(
        self, request: AuthRefreshTokenRequest, context: grpc.aio.ServicerContext
    ) -> AuthRefreshTokenReply:
        refresh_token = request.refresh_token
        if data := await self.auth_backend.refresh(request.uid, refresh_token):
            access_token, refresh_token = data
            return AuthRefreshTokenReply(
                status=AUTH_SUCCESS,
                access_token=access_token,
                refresh_token=refresh_token,
            )
        else:
            # TODO add timeout check, so user just retry
            logger.warning("refresh_token is mismatched")
            return AuthRefreshTokenReply(status=AUTH_FAILED)
