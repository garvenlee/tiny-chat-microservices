from typing import Optional
from logging import getLogger

from chatp.proto.services.transfer.msg_data_pb2 import ClientMsgData
from chatp.proto.services.transfer.upstream_pb2_grpc import UpstreamTransferStub
from chatp.proto.services.transfer.upstream_pb2 import (
    DeliverUpMsgRequest,
    DeliverUpMsgReply,
)
from chatp.rpc.grpc_wrapper import depend
from chatp.rpc.grpc_service import GrpcService
from chatp.rpc.model import CallResult, GrpcStatus, GRPC_SUCCESS, GRPC_TIMEOUT

logger = getLogger("UpstreamTransferService")
logger.setLevel(10)


class UpstreamTransferService(GrpcService):
    __bind_stub__ = UpstreamTransferStub

    wrapped_directly = ("DeliverMessage",)
    customization = ("deliver_message",)

    # meth signature
    async def DeliverMessage(
        self, request: DeliverUpMsgRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[DeliverUpMsgReply]]:
        pass

    @depend(stub_cls=UpstreamTransferStub)
    async def deliver_message(self, data: ClientMsgData, *, timeout: int = 5) -> int:
        result: CallResult = await self.DeliverMessage(
            request=DeliverUpMsgRequest(message_data=data), timeout=timeout
        )
        if (status := result.status) is GRPC_SUCCESS:
            return result.data.message_id
        elif status is GRPC_TIMEOUT:
            logger.warning("Found timeout in TransferMessage")
            return 0
        else:
            logger.exception(f"Found unexpected exception: {result.info}")
            return 0
