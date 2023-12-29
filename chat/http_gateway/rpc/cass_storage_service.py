from logging import getLogger
from grpc.aio import StreamStreamCall, Metadata
from chatp.proto.services.transfer.cass_storage_pb2 import CassSessionRequest
from chatp.proto.services.transfer.cass_storage_pb2_grpc import CassStorageStub
from chatp.rpc.grpc_service import GrpcService


logger = getLogger("CassMessageService")
logger.setLevel(10)


class CassMessageService(GrpcService):
    __bind_stub__ = CassStorageStub

    reuse = ("ReadSession",)

    def ReadSession(
        self, request: CassSessionRequest, metadata: Metadata, **kwargs
    ) -> StreamStreamCall:
        pass
