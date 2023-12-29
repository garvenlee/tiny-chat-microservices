from typing import Optional
from chatp.rpc.grpc_service import GrpcService
from chatp.rpc.model import CallResult, GrpcStatus
from chatp.proto.services.auth.auth_user_pb2_grpc import AuthUserStub
from chatp.proto.services.auth.auth_user_pb2 import (
    AuthLoginRequest,
    AuthLoginReply,
    AuthRegisterRequest,
    AuthRegisterReply,
    AuthRegisterConfirmRequest,
    AuthRegisterConfirmReply,
    AuthRefreshTokenRequest,
    AuthRefreshTokenReply,
    AuthTokenRequest,
    AuthTokenReply,
)


class AuthService(GrpcService):
    __bind_stub__ = AuthUserStub

    wrapped_with_combination = (
        "AuthLogin",
        "AuthRegister",
        "AuthRegisterConfirm",
        "AuthRefresh",
        "AuthToken",
    )

    # meth signature
    async def AuthLogin(
        self, request: AuthLoginRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[AuthLoginReply]]:
        pass

    async def AuthRegister(
        self, request: AuthRegisterRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[AuthRegisterReply]]:
        pass

    async def AuthRegisterConfirm(
        self, request: AuthRegisterConfirmRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[AuthRegisterConfirmReply]]:
        pass

    async def AuthRefresh(
        self, request: AuthRefreshTokenRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[AuthRefreshTokenReply]]:
        pass

    async def AuthToken(
        self, request: AuthTokenRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[AuthTokenReply]]:
        pass
