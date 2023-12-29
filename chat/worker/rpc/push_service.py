from typing import Optional
from logging import getLogger

from chatp.proto.services.push.push_pb2_grpc import PushStub
from chatp.proto.services.push.push_pb2 import (
    PubNotification,
    PubEventType,
    PubNotificationAck,
    PubNotificationHeader,
    PUSH_SUCCESS,
    PUSH_TIMEOUT,
    PUSH_OFFLINE,
)
from chatp.rpc.grpc_wrapper import depend
from chatp.rpc.grpc_service import GrpcService
from chatp.rpc.model import CallResult, GrpcStatus, GRPC_SUCCESS, GRPC_TIMEOUT


logger = getLogger("PushService")
logger.setLevel(10)


class PushService(GrpcService):
    __bind_stub__ = PushStub

    wrapped_directly = ("PublishNotification",)
    customization = ("push_data",)

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
        timeout: int | float,
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
            if (status := result.data.status) is PUSH_SUCCESS:
                logger.info("Pushed one message successfully.")
                return True
            elif status is PUSH_OFFLINE:  # offline, do nothing
                logger.info(
                    "Found user offline in GrpcCall<PushService.PublishNotification>"
                )
                return True
            elif status is PUSH_TIMEOUT:
                logger.exception(
                    "GrpcCall<PushService.PublishNotification> returned PUSH_TIMEOUT",
                    exc_info=None,
                )
            else:
                logger.error(
                    "GrpcCall<PushService.PublishNotification> returned PUSH_FAILED",
                    exc_info=None,
                )
        elif grpc_status is GRPC_TIMEOUT:
            logger.exception(
                "Found timeout when calling GrpcCall<PushService.PublishNotification>",
                exc_info=None,
            )
        else:  # Grpc-Call Failed?
            logger.error(
                "Found unknown error when calling GrpcCall<PushService.PublishNotification>",
                exc_info=None,
            )
        return False
