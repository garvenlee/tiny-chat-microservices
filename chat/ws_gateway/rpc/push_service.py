from logging import getLogger
from typing import AsyncIterable, Optional

from grpc.aio import StreamStreamCall, Metadata

from chatp.proto.services.push.push_pb2_grpc import PushStub
from chatp.proto.services.push.push_pb2 import (
    PUSH_SUCCESS,
    PUSH_TIMEOUT,
    PUSH_OFFLINE,
    PubEventType,
    PubNotification,
    PubNotificationAck,
    PubNotificationHeader,
    ConsumerFeedback,
)
from chatp.rpc.grpc_wrapper import depend
from chatp.rpc.grpc_service import GrpcService
from chatp.rpc.model import *

logger = getLogger("PushService")
logger.setLevel(10)


class PushService(GrpcService):
    __bind_stub__ = PushStub
    service_consumer = None  # needs to bind

    reuse = ("SubscribeStream",)
    wrapped_directly = ("PublishNotification",)
    customization = ("push_data",)

    def SubscribeStream(
        self,
        request_iterator: AsyncIterable[ConsumerFeedback],
        metadata: Metadata,
        **kwargs,
    ) -> StreamStreamCall:
        pass

    async def PublishNotification(
        self, request: PubNotification
    ) -> CallResult[GrpcStatus, Optional[str], Optional[PubNotificationAck]]:
        pass

    @depend(stub_cls=PushStub)
    async def push_data(
        self,
        data_type: PubEventType,
        address_id: int,
        payload: bytes,
        *,
        timeout: int | float = 8,
    ) -> bool:
        result: CallResult = await self.PublishNotification(
            request=PubNotification(
                header=PubNotificationHeader(
                    data_type=data_type, address_id=address_id
                ),
                payload=payload,
            ),
            timeout=timeout,
        )

        if (grpc_status := result.status) is GRPC_SUCCESS:
            if (status := result.data.status) in (PUSH_SUCCESS, PUSH_OFFLINE):
                logger.info("GrpcCall<PushSerivice.PublishNotification> is successful")
                return True
            elif status is PUSH_TIMEOUT:
                logger.warning(
                    "GrpcCall<PushSerivice.PublishNotification> returned PUSH_TIMEOUT"
                )
            else:
                logger.error(
                    "GrpcCall<PushSerivice.PublishNotification> returned PUSH_FAILED"
                )
        elif grpc_status is GRPC_TIMEOUT:
            logger.warning(
                "GrpcCall<PushSerivice.PublishNotification> found GRPC_TIMEOUT"
            )
        else:
            logger.error("GrpcCall<PushSerivice.PublishNotification> found GRPC_FAILED")
        return False
