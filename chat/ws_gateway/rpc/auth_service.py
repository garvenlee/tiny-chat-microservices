import logging
from typing import Optional

from chatp.rpc.grpc_service import GrpcService
from chatp.proto.services.auth.auth_user_pb2_grpc import AuthUserStub
from chatp.proto.services.auth.auth_user_pb2 import AuthTokenRequest, AuthTokenReply
from chatp.rpc.model import CallResult, GrpcStatus

logger = logging.getLogger("AuthService")


class AuthService(GrpcService):
    __bind_stub__ = AuthUserStub

    wrapped_with_combination = ("AuthToken",)

    async def AuthToken(
        self, request: AuthTokenRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[AuthTokenReply]]:
        pass
