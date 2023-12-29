from typing import Optional

from chatp.rpc.grpc_service import GrpcService
from chatp.rpc.model import CallResult, GrpcStatus
from chatp.proto.services.friend.friend_pb2_grpc import FriendStub
from chatp.proto.services.friend.friend_pb2 import (
    FriendRequest,
    FriendRequestBatch,
    FriendRequestReply,
    FriendConfirm,
    FriendConfirmReply,
)


class UserService(GrpcService):
    __bind_stub__ = FriendStub

    wrapped_directly = ("AddFriend", "ConfirmFriend")

    # meth signature
    async def AddFriend(
        self, request: FriendRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[FriendRequestReply]]:
        pass

    async def ConfirmFriend(
        self, request: FriendConfirm
    ) -> CallResult[GrpcStatus, Optional[str], Optional[FriendConfirmReply]]:
        pass

    async def AddFriendBatch(
        self, batch: FriendRequestBatch
    ) -> CallResult[GrpcStatus, Optional[str], Optional[FriendRequestReply]]:
        pass
