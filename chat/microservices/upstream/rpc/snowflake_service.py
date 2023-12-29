from typing import Optional

from chatp.proto.services.snowflake.snowflake_pb2_grpc import SnowflakeStub
from chatp.proto.services.snowflake.snowflake_pb2 import (
    SnowflakeRequest,
    SnowflakeReply,
)

from chatp.rpc.grpc_service import GrpcService
from chatp.rpc.model import CallResult, GrpcStatus


class SnowflakeService(GrpcService):
    __bind_stub__ = SnowflakeStub

    wrapped_with_combination = ("flickClock",)

    # meth signature
    async def flickClock(
        self, request: SnowflakeRequest
    ) -> CallResult[GrpcStatus, Optional[str], Optional[SnowflakeReply]]:
        pass
