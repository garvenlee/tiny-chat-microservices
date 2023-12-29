from typing import Optional
from logging import getLogger

from chatp.proto.services.transfer.msg_data_pb2 import ServerMsgData
from chatp.proto.services.transfer.cass_storage_pb2 import (
    CassMsgRequest,
    CassMsgReply,
    CassInboxRequest,
    CassInboxReply,
    CASS_MSG_SUCCESS,
    CASS_MSG_TIMEOUT,
)
from chatp.proto.services.transfer.cass_storage_pb2_grpc import CassStorageStub
from chatp.rpc.grpc_service import GrpcService
from chatp.rpc.grpc_wrapper import depend
from chatp.rpc.model import CallResult, GrpcStatus, GRPC_SUCCESS, GRPC_TIMEOUT

logger = getLogger("CassMessageService")
logger.setLevel(10)


class CassMessageService(GrpcService):
    __bind_stub__ = CassStorageStub

    wrapped_directly = ("WriteToInbox", "ReadInbox")
    customization = ("write_to_inbox", "read_inbox")

    async def WriteToInbox(
        self, request: CassMsgRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[CassMsgReply]]:
        pass

    async def ReadInbox(
        self, request: CassInboxRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[CassInboxReply]]:
        pass

    @depend(stub_cls=CassStorageStub)
    async def write_to_inbox(
        self,
        delivery_id: int,
        message_id: int,
        message_data: ServerMsgData,
        *,
        timeout: int | float = 8,
    ):
        result: CallResult = await self.WriteToInbox(
            request=CassMsgRequest(
                delivery_id=delivery_id,
                message_id=message_id,
                message_data=message_data,
            ),
            timeout=timeout,
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
        elif status is GRPC_TIMEOUT:
            logger.exception("GrpcCall<WriteToInbox> is Timeout", exc_info=False)
        else:
            logger.exception("GrpcCall<WriteToInbox> Failed", exc_info=False)

        return False

    @depend(stub_cls=CassStorageStub)
    async def read_inbox(
        self, address_id: int, last_max_msg_id: int, *, timeout: int | float = 12
    ) -> Optional[list[ServerMsgData]]:
        result: CallResult = await self.ReadInbox(
            request=CassInboxRequest(
                uid=address_id,
                last_max_msg_id=last_max_msg_id,
            ),
            timeout=timeout,
        )
        if (status := result.status) is GRPC_SUCCESS:
            data = result.data
            if (code := data.code) is CASS_MSG_SUCCESS:
                logger.info("Cassandra Read Successfully")
                return data.messages  # list[ServerMsgData]
            elif code is CASS_MSG_TIMEOUT:
                logger.exception("Cassandra Read Timeout", exc_info=False)
            else:
                logger.exception("Cassandra Read Failed", exc_info=False)
        elif status is GRPC_TIMEOUT:
            logger.exception("GrpcCall<ReadInbox> is Timeout", exc_info=False)
        else:
            logger.exception("GrpcCall<ReadInbox> Failed", exc_info=False)

        return
