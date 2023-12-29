from typing import Optional
from logging import getLogger

from chatp.proto.services.transfer.msg_data_pb2 import ServerMsgData
from chatp.proto.services.transfer.downstream_pb2_grpc import DownstreamTransferStub
from chatp.proto.services.transfer.downstream_pb2 import (
    READ_MODEL_SUCCESS,
    ReadModelEventType,
    ReadModelEvent,
    DeliverReadEventReply,
)
from chatp.rpc.grpc_wrapper import depend
from chatp.rpc.grpc_service import GrpcService
from chatp.rpc.model import CallResult, GrpcStatus, GRPC_SUCCESS, GRPC_TIMEOUT

logger = getLogger("DownstreamTransferService")
logger.setLevel(10)


class DownstreamTransferService(GrpcService):
    __bind_stub__ = DownstreamTransferStub

    wrapped_directly = ("DeliverReadEvent",)
    customization = ("deliver_read_event",)

    # meth signature
    async def DeliverReadEvent(
        self, request: ReadModelEvent
    ) -> CallResult[GrpcStatus, Optional[str], Optional[DeliverReadEventReply]]:
        pass

    @depend(stub_cls=DownstreamTransferStub)
    async def deliver_read_event(
        self,
        event_tp: ReadModelEventType,
        delivery_id: int,
        data: ServerMsgData,
        *,
        timeout: int = 5,
    ) -> int:
        result: CallResult = await self.DeliverReadEvent(
            request=ReadModelEvent(
                event_tp=event_tp, delivery_id=delivery_id, message=data
            ),
            timeout=timeout,
        )
        if (status := result.status) is GRPC_SUCCESS:
            return result.data.status is READ_MODEL_SUCCESS
        elif status is GRPC_TIMEOUT:
            logger.warning("Found timeout in DeliverReadEvent")
            return False
        else:
            logger.exception(
                f"Found unexpected exception: {result.info}", exc_info=None
            )
            return False
