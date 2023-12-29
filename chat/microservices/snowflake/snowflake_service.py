from logging import getLogger
from asyncio import sleep

import grpc
from snowflake import SnowflakeGenerator

from chatp.proto.services.snowflake.snowflake_pb2_grpc import (
    SnowflakeServicer as ProtoService,
)
from chatp.proto.services.snowflake.snowflake_pb2 import (
    SnowflakeRequest,
    SnowflakeReply,
    BusinessKind,
    SNOWFLAKE_MESSAGE,
    SNOWFLAKE_SESSION,
    SNOWFLAKE_USER_DEFINED,
)

logger = getLogger("SnowflakeService")


class SnowflakeServicer(ProtoService):
    def __init__(self, id_generator: SnowflakeGenerator):
        self.id_generator = id_generator
        self.id_generate = id_generator.__next__

    async def flickClock(
        self, request: SnowflakeRequest, context: grpc.aio.ServicerContext
    ):
        kind = request.kind  # BusinessKind s.t. SESSION, MESSAGE
        logger.warning(f"Received one id request: {BusinessKind.Name(kind)}")

        # Ignore OverflowError currently
        id_generate = self.id_generate
        while (snowflake := id_generate()) is None:
            await sleep(0)
            if context.cancelled():
                return

        if not context.cancelled():
            return SnowflakeReply(snowflake_id=snowflake)
