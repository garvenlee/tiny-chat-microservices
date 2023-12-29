from typing import Optional

from chatp.proto.services.user.user_pb2_grpc import UserStub
from chatp.proto.services.user.user_pb2 import (
    UserLoginRequest,
    UserLoginReply,
    UserRegisterRequest,
    UserRegisterReply,
    UserLogoutRequest,
    UserLogoutReply,
    UserQueryRequest,
    UserQueryReply,
    UserRegisterConfirmRequest,
    UserRegisterConfirmReply,
)

from chatp.rpc.grpc_service import GrpcService
from chatp.rpc.model import CallResult, GrpcStatus


class UserService(GrpcService):
    __bind_stub__ = UserStub

    wrapped_with_combination = (
        "UserLogin",
        "UserRegister",
        "UserQuery",
        "UserRegisterConfirm",
    )

    # meth signature
    async def UserLogin(
        self, request: UserLoginRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[UserLoginReply]]:
        pass

    async def UserRegister(
        self, request: UserRegisterRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[UserRegisterReply]]:
        pass

    async def UserLogout(
        self, request: UserLogoutRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[UserLogoutReply]]:
        pass

    async def UserQuery(
        self, request: UserQueryRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[UserQueryReply]]:
        pass

    async def UserRegisterConfirm(
        self, request: UserRegisterConfirmRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[UserRegisterConfirmReply]]:
        pass
