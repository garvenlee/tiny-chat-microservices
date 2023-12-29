from time import monotonic
from logging import getLogger
from enum import IntEnum
from functools import partial
from collections import defaultdict

from attrs import define, field
from asyncio import Event as AsyncIOEvent, TimeoutError as AsyncIOTimeoutError, wait_for
from grpc.aio import ServicerContext

from chatp.manager.grpc_client import GrpcClientManager
from chatp.proto.services.transfer.msg_data_pb2 import ClientMsgData, RStreamMsgData
from chatp.proto.services.transfer.upstream_pb2 import (
    DeliverUpMsgRequest,
    DeliverUpMsgReply,
    UPSTREAM_DELIVERY_SUCCESS,
    UPSTREAM_DELIVERY_TIMEOUT,
    UPSTREAM_DELIVERY_FAILED,
)
from chatp.proto.services.transfer.upstream_pb2_grpc import (
    UpstreamTransferServicer as ProtoService,
)
from chatp.rpc.model import GRPC_TIMEOUT, GRPC_SUCCESS, CallResult

from rmq.service import RMQService, MessageTracerBase
from rpc.snowflake_service import SnowflakeService

logger = getLogger("UpstreamTransferService")


class PublishState(IntEnum):
    INFLIGHT = 1
    SUCCESS = 2
    FAILURE = 3


@define(slots=True)
class MessageMetadata:
    message_id: int
    timestamp: float = field(factory=monotonic)
    state: PublishState = field(default=PublishState.INFLIGHT)
    event: AsyncIOEvent = field(factory=AsyncIOEvent)

    @property
    def is_valid(self):
        return (
            self.state is PublishState.SUCCESS
            and 0 <= monotonic() - self.timestamp < 30
        )

    def reset(self, message_id: int):
        self.message_id = message_id
        self.timestamp = monotonic()
        self.state = PublishState.INFLIGHT
        self.event.clear()


class MessageTracer(MessageTracerBase):
    __slots__ = "cache"

    def __init__(self):
        self.cache: defaultdict[int, dict[int, MessageMetadata]] = defaultdict(dict)

    def on_publish_start(self, rsq_data: RStreamMsgData):
        metadata = self.cache[rsq_data.data.sender_id].get(rsq_data.delivery_id)
        if metadata is None:
            metadata = MessageMetadata(rsq_data.message_id)
        else:
            metadata.reset(rsq_data.message_id)

    def on_publish_succee(self, rsq_data: RStreamMsgData):
        metadata = self.cache[rsq_data.data.sender_id][rsq_data.delivery_id]
        metadata.state = PublishState.SUCCESS
        metadata.event.set()

    def on_publish_failure(self, rsq_data: RStreamMsgData):
        metadata = self.cache[rsq_data.data.sender_id][rsq_data.delivery_id]
        metadata.state = PublishState.FAILURE
        metadata.event.set()

    async def conflict_check(
        self, rsq_data: RStreamMsgData, *, timeout: int | float
    ) -> int:
        metadata = self.cache[rsq_data.data.sender_id].get(rsq_data.delivery_id)
        if metadata is not None:
            if metadata.is_valid:
                return metadata.message_id

            if metadata.state is PublishState.INFLIGHT:
                try:
                    await wait_for(metadata.event.wait(), timeout=timeout)
                except AsyncIOTimeoutError:
                    return -1
                else:
                    if metadata.is_valid:  # recheck
                        return metadata.message_id

        # here, means metadata is None or metadata.state is failure
        # then it's safe to publish again
        return 0


class UpstreamTransferServicer(ProtoService):
    def __init__(self, grpc_manager: GrpcClientManager, rmq_service: RMQService):
        self.id_service_getter = partial(grpc_manager.find_service, "SnowflakeService")

        tracer = MessageTracer()
        rmq_service.bind_tracer(tracer)
        rmq_service.bind_route_func(lambda rsq_msg: str(rsq_msg.data.session_id))

        self.conflict_check = tracer.conflict_check
        self.pub_to_rmq = rmq_service.publish_message

    async def DeliverMessage(
        self, request: DeliverUpMsgRequest, context: ServicerContext
    ) -> DeliverUpMsgReply:
        request_data: ClientMsgData = request.message_data
        msg, delivery_id = request_data.data, request_data.delivery_id

        rsq_data = RStreamMsgData(data=msg, delivery_id=delivery_id)
        message_id = await self.conflict_check(
            rsq_data, timeout=context.time_remaining()
        )  # may be cancelled by the peer
        if message_id == 0:
            id_service: SnowflakeService = self.id_service_getter(
                hash_key=str(msg.session_id)
            )
            if id_service is None:
                return DeliverUpMsgReply(code=UPSTREAM_DELIVERY_FAILED)

            result: CallResult = await id_service.flickClock(
                kind=0, timeout=context.time_remaining()
            )  # may be cancelled by the peer
            if (grpc_status := result.status) is GRPC_SUCCESS:
                logger.info("Flick one SnowflakeId successfully")
                rsq_data.message_id = message_id = result.data.snowflake_id
                success = await self.pub_to_rmq(
                    rsq_data, timeout=context.time_remaining()
                )
                if success:
                    logger.info("Publish one message successfully")
                    reply = DeliverUpMsgReply(
                        code=UPSTREAM_DELIVERY_SUCCESS, message_id=message_id
                    )
                else:  # means timeout, in case, s.t. Server is closing
                    reply = DeliverUpMsgReply(code=UPSTREAM_DELIVERY_TIMEOUT)
            elif grpc_status is GRPC_TIMEOUT:
                logger.warning("Id Service is busy now")
                reply = DeliverUpMsgReply(code=UPSTREAM_DELIVERY_TIMEOUT)
            else:
                logger.warning("Found unexpected exception: %s", result.info)
                reply = DeliverUpMsgReply(code=UPSTREAM_DELIVERY_FAILED)

            if not context.cancelled():
                return reply

        elif message_id > 0:
            logger.info("Fast return the message_id")
            return DeliverUpMsgReply(message_id=message_id)
        else:
            # TODO If it's always idle here ?
            logger.exception(
                "Wait again, but still dont get PublishConfirm", exc_info=False
            )
            return DeliverUpMsgReply(code=UPSTREAM_DELIVERY_TIMEOUT)

    # TODO User send PubEventAckFromUser to the gateway, then gateway needs to notify
    #   TransferServce to clear unnecessary items in tracer
    async def CompactTracer(self, request, context):
        pass
