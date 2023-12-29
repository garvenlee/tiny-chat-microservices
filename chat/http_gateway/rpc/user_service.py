from typing import Optional

from chatp.rpc.grpc_service import GrpcService
from chatp.rpc.model import CallResult, GrpcStatus
from chatp.proto.services.user.user_pb2_grpc import UserStub
from chatp.proto.services.user.user_pb2 import UserQueryRequest, UserQueryReply
from chatp.proto.services.friend.friend_pb2_grpc import FriendStub
from chatp.proto.services.friend.friend_pb2 import FriendListRequest, FriendListReply


class UserService(GrpcService):
    __bind_stub__ = (UserStub, FriendStub)

    wrapped_with_combination = ("UserQuery", "GetFriendList")

    async def UserQuery(
        self, request: UserQueryRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[UserQueryReply]]:
        pass

    async def GetFriendList(
        self, request: FriendListRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[FriendListReply]]:
        pass
