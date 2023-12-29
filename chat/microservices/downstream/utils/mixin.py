from logging import getLogger
from typing import Optional
from functools import partial
from asyncio import BaseEventLoop, get_running_loop

from chatp.redis.model import REDIS_SUCCESS
from chatp.redis.client import RedisClient
from chatp.manager.grpc_client import GrpcClientManager
from chatp.proto.services.transfer.msg_data_pb2 import ServerMsgData
from chatp.proto.services.push.push_pb2 import PUSH_USER_MESSAGE, PubUserMessage

from .task_manager import TaskManager
from rmq.service import RMQService
from rpc.push_service import PushService

logger = getLogger("PushMixin")
logger.setLevel(10)


class PushMixin:
    def __init__(
        self,
        grpc_manager: GrpcClientManager,
        redis_client: RedisClient,
        rmq_pusher: RMQService,
        *,
        broker_id: str,
        loop: Optional[BaseEventLoop] = None,
    ):
        self.push_service_getter = partial(grpc_manager.find_service, "PushService")
        self.redis_hlen = redis_client.redis_hlen
        self.send_to_push = partial(
            rmq_pusher.send_to_push,
            user_id=None,
            app_id=broker_id,
        )

        if loop is None:
            loop = get_running_loop()
        self.task_manager = TaskManager(loop)
        self.task_factory = self.task_manager.create_task

    async def user_online_check(self, uid: int):
        data, status = await self.redis_hlen(
            f"chatp:user:gateway_addr:uid:{uid}", timeout=3
        )
        return data > 0 if status is REDIS_SUCCESS else None

    async def push_to_gateway(
        self,
        address_id: int,
        message: ServerMsgData,
        *,
        hash_key: str,
        timeout: int | float = 5,
    ) -> bool:
        service: Optional[PushService] = self.push_service_getter(hash_key=hash_key)
        if service is None:
            logger.warning(
                "PushService is unavailable temporarily, then needs to push_to_rmq..."
            )
            return False

        return await service.push_data(
            data_type=PUSH_USER_MESSAGE,
            address_id=address_id,
            payload=message.SerializeToString(),
            timeout=timeout,
        )

    async def push_message(
        self,
        address_id: int,
        message: ServerMsgData,
        *,
        timeout: int | float = 5,
    ):
        logger.info("One message is ready to be delivered into AsyncNotify Queue")
        try:
            await self.send_to_push(
                PubUserMessage(
                    address_id=address_id,
                    payload=message.SerializeToString(),
                ).SerializeToString(),
                timeout=timeout,
            )
            return True
        except BaseException as exc:
            logger.warning("One message failed to push anyway: %s", exc, exc_info=exc)
            return False

    async def ready_to_push(
        self,
        address_id: int,
        push_entity: ServerMsgData,
        *,
        hash_key: str,
        timeout: int | float = 5,
    ):
        if exists := await self.user_online_check(address_id):
            if await self.push_to_gateway(
                address_id, push_entity, hash_key=hash_key, timeout=timeout
            ):
                logger.info("Push one message successfully")
                return True  # fast return if push operation is successful
        elif exists is not None:  # UserOffline
            logger.info(f"Found address-user[{address_id}] is offline, no need to push")
            return True
        else:
            logger.warning("Found Redis Timeout or Failed")

        # If failed to push, then publish it to plain MQ, wait PushService to consume it
        return await self.push_message(address_id, push_entity)  # default timeout 5s
