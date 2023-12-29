from logging import getLogger
from functools import partial
from typing import Optional

from grpc.aio import ServicerContext as AioServicerContext
from aio_pika.message import IncomingMessage

from chatp.manager.grpc_client import GrpcClientManager
from chatp.redis.client import RedisClient
from chatp.proto.services.transfer.downstream_pb2 import (
    PullInboxRequest,
    PullInboxReply,
    ReadModelEvent,
    READ_MODEL_SUCCESS,
    READ_MODEL_TIMEOUT,
    READ_MODEL_FAILED,
    READ_MODEL_SINGLE_CHAT,
    DeliverReadEventReply,
)
from chatp.proto.services.transfer.downstream_pb2_grpc import (
    DownstreamTransferServicer as ProtoService,
)

from utils.mixin import PushMixin
from rmq.service import RMQService
from rpc.cass_storage_service import CassMessageService

logger = getLogger("DownstreamTransferService")
logger.setLevel(10)


class DownstreamTransferServicer(ProtoService, PushMixin):
    def __init__(
        self,
        grpc_manager: GrpcClientManager,
        redis_client: RedisClient,
        rmq_pusher: RMQService,
        broker_id: str,
    ):
        super(ProtoService, self).__init__(
            grpc_manager,
            redis_client,
            rmq_pusher,
            broker_id=broker_id,
        )

        self.cass_message_service_getter: Optional[CassMessageService] = partial(
            grpc_manager.find_service, "CassMessageService"
        )
        self.handlers = {READ_MODEL_SINGLE_CHAT: self.handle_inbox}

    async def handle_inbox(self, event: ReadModelEvent):
        service: Optional[CassMessageService] = self.cass_message_service_getter()
        if service is None:
            logger.warning("CassStorageService is unavailable temporarily")
            return False

        server_msg = event.message
        if await service.write_to_inbox(
            delivery_id=event.delivery_id,
            message_id=server_msg.message_id,
            message_data=server_msg.data,
        ):
            logger.info("Write one message to Inbox successfully")
            return True
        else:
            logger.warning("Found Cassandra Write failed")
            return False

    # TODO Eventual Consistency
    # Found UserOffline when SendToPush, then user became online and pull Inbox
    # but ReadModelEvent is still not be handled, so this message will be missing
    async def consume_event(self, message: IncomingMessage):
        logger.info("Received one message from ReadModelQueue")
        event = ReadModelEvent.FromString(message.body)
        if await self.handle_inbox(event):
            # Then needs to push
            server_msg = event.message
            msg_data = server_msg.data
            if await self.ready_to_push(
                msg_data.receiver_id,
                server_msg,
                hash_key=str(msg_data.session_id),
                timeout=5,
            ):
                await message.ack()
                return

        await message.reject(requeue=True)

    async def DeliverReadEvent(
        self, request: ReadModelEvent, context: AioServicerContext
    ) -> DeliverReadEventReply:
        if (event_tp := request.event_tp) is READ_MODEL_SINGLE_CHAT:
            if await self.handle_inbox(request):
                # Then needs to push
                server_msg = request.message
                msg_data = server_msg.data
                if await self.ready_to_push(
                    msg_data.receiver_id,
                    server_msg,
                    hash_key=str(msg_data.session_id),
                    timeout=context.time_remaining(),  # default 5
                ):
                    return DeliverReadEventReply(status=READ_MODEL_SUCCESS)

        return DeliverReadEventReply(status=READ_MODEL_FAILED)

    async def PullInboxMsg(
        self, request: PullInboxRequest, context: AioServicerContext
    ) -> PullInboxReply:
        service: Optional[CassMessageService] = self.cass_message_service_getter()
        if service is None:
            return PullInboxReply(status=READ_MODEL_FAILED)

        # TODO Two data transmissions, maybe add session connector in ReadModel later
        data = await service.read_inbox(
            request.uid,
            request.received_max_msg_id,
            timeout=context.time_remaining(),  # default 5
        )
        if data is None:
            return PullInboxReply(status=READ_MODEL_FAILED)

        return PullInboxReply(status=READ_MODEL_SUCCESS, messages=data)

    async def PullFullSessionMsg(self, request, context: AioServicerContext):
        pass
