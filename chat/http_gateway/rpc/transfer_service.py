from typing import Optional
from chatp.rpc.grpc_service import GrpcService
from chatp.rpc.model import CallResult, GrpcStatus
from chatp.proto.services.transfer.downstream_pb2_grpc import DownstreamTransferStub
from chatp.proto.services.transfer.downstream_pb2 import (
    PullInboxRequest,
    PullInboxReply,
)


class DownstreamTransferService(GrpcService):
    __bind_stub__ = DownstreamTransferStub

    wrapped_directly = ("PullInboxMsg",)

    # meth signature
    async def PullInboxMsg(
        self, request: PullInboxRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[PullInboxReply]]:
        pass
