from typing import Optional
from logging import getLogger

from chatp.proto.services.transfer.cass_storage_pb2 import (
    CassMsgRequest,
    CassMsgReply,
    CASS_MSG_SUCCESS,
    CASS_MSG_TIMEOUT,
)
from chatp.proto.services.transfer.cass_storage_pb2_grpc import CassStorageStub
from chatp.rpc.grpc_wrapper import depend
from chatp.rpc.grpc_service import GrpcService
from chatp.rpc.model import CallResult, GrpcStatus, GRPC_SUCCESS, GRPC_TIMEOUT


logger = getLogger("CassMessageService")
logger.setLevel(10)


class CassMessageService(GrpcService):
    __bind_stub__ = CassStorageStub

    wrapped_directly = ("WriteToSession", "WriteToInbox")
    customization = ("write_to_session", "write_to_inbox")

    async def WriteToSession(
        self, request: CassMsgRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[CassMsgReply]]:
        pass

    async def WriteToInbox(
        self, request: CassMsgRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[CassMsgReply]]:
        pass

    @depend(stub_cls=CassStorageStub)
    async def write_to_session(
        self,
        cass_msg: CassMsgRequest,
        *,
        timeout: int | float = 8,
    ):
        result: CallResult = await self.WriteToSession(
            request=cass_msg, timeout=timeout
        )
        if (status := result.status) is GRPC_SUCCESS:
            code = result.data.code
            if code is CASS_MSG_SUCCESS:
                logger.info("Cassandra Write Successfully")
                return True
            elif code is CASS_MSG_TIMEOUT:
                logger.exception("Cassandra Write Timeout", exc_info=False)
            else:
                logger.exception("Cassandra Write Failed", exc_info=False)
        elif status is GRPC_TIMEOUT:  # DEADLINE_EXCEEDED
            logger.exception("GrpcCall<SaveMessage> is Timeout", exc_info=False)
        else:  # AioRpcError but not DEADLINE_EXCEEDED | Cancelled by caller
            logger.exception("GrpcCall<SaveMessage> Failed", exc_info=False)

        return False

    @depend(stub_cls=CassStorageStub)
    async def write_to_inbox(
        self,
        cass_msg: CassMsgRequest,
        *,
        timeout: int | float = 8,
    ):
        result: CallResult = await self.WriteToInbox(request=cass_msg, timeout=timeout)
        if (status := result.status) is GRPC_SUCCESS:
            code = result.data.code
            if code is CASS_MSG_SUCCESS:
                logger.info("Cassandra Write Successfully")
                return True
            elif code is CASS_MSG_TIMEOUT:
                logger.exception("Cassandra Write Timeout", exc_info=None)
            else:
                logger.exception("Cassandra Write Failed", exc_info=None)
        elif status is GRPC_TIMEOUT:
            logger.exception("GrpcCall<SaveMessage> is Timeout", exc_info=None)
        else:
            logger.exception("GrpcCall<SaveMessage> Failed", exc_info=None)

        return False
