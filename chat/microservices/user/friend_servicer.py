from logging import getLogger
from typing import cast, Optional

from grpc.aio import ServicerContext as AioServicerContext

from chatp.database.model import *
from chatp.database.exceptions import TransactionFailed
from chatp.proto.services.friend.friend_pb2_grpc import FriendServicer as ProtoServicer
from chatp.proto.services.friend.friend_pb2 import (
    ACCEPTED,
    REJECTED,
    IGNORED,
    FRIEND_SUCCESS,
    FRIEND_TIMEOUT,
    FRIEND_FAILED,
    FriendRequest,
    FriendRequestReply,
    FriendRequestBatch,
    FriendConfirm,
    FriendConfirmReply,
    RelationLink,
    FriendDetailedInfo,
    FriendListRequest,
    FriendListReply,
)
from executor import DbExecutor

logger = getLogger("FriendServicer")
logger.setLevel(10)


class FriendServicer(ProtoServicer):
    def __init__(self, executor: DbExecutor):
        self.create_friend_request = executor.create_friend_request
        self.reject_friend_request = executor.reject_friend_request
        self.ignore_friend_request = executor.ignore_friend_request

        self.create_friend = executor.create_friend
        self.delete_friend = executor.delete_friend
        self.block_friend = executor.block_friend
        # self.batch_process = executor.batch_process

        self.get_friends = executor.get_friends

    async def AddFriend(
        self, request: FriendRequest, context: AioServicerContext
    ) -> FriendRequestReply:
        # TODO A has sent request to B, then B send request to A?
        # TODO client: pre-check user in friend
        link: RelationLink = request.link
        result, delay = await self.create_friend_request(
            request_id=link.request_id,
            address_id=link.address_id,
            request_msg=request.request_msg or None,
            timeout=context.time_remaining(),
        )

        if result is None:
            return FriendRequestReply(status=FRIEND_FAILED)

        logger.warning(f"Add Friend consumes: {delay}")
        result = cast(ExecutionResult, result)
        status = result.status
        if status is DB_SUCCESS:
            reply = FriendRequestReply(status=FRIEND_SUCCESS)
        elif status is DB_TIMEOUT_HANDLING:
            logger.info("timeout when waiting db_service to return a result")
            reply = FriendRequestReply(status=FRIEND_TIMEOUT)
        else:
            logger.info(f"{result.msg}")
            reply = FriendRequestReply(status=FRIEND_FAILED)

        if not context.cancelled():
            return reply

    async def AddFriendBatch(
        self, batch: FriendRequestBatch, context: AioServicerContext
    ) -> FriendRequestReply:
        pass
        requests: list[FriendRequest] = batch.requests

        result: Optional[ExecutionResult] = await self.create_friend_in_batch(
            table="friend_requests",
            columns=("request_id", "address_id", "request_msg", "created_at"),
            sequence_values=tuple(
                (
                    request.request_id,
                    request.address_id,
                    request.request_msg,
                )
                for request in requests
            ),
            timeout=6,
        )

        if result is None:
            return FriendRequestReply(status=FRIEND_FAILED)

        status = result.status
        if status is DB_SUCCESS:
            return FriendRequestReply(status=FRIEND_SUCCESS)
        elif status is DB_TIMEOUT_PENDING:
            logger.info("timeout when waiting db_service to handle a InsertTask")
            return FriendRequestReply(status=FRIEND_TIMEOUT)
        elif status is DB_TIMEOUT_HANDLING:
            logger.info("timeout when waiting db_service to return a result")
            return FriendRequestReply(status=FRIEND_TIMEOUT)
        else:
            logger.info(f"{result.msg}")
            return FriendRequestReply(status=FRIEND_FAILED)

    async def ConfirmFriend(
        self, request: FriendConfirm, context: AioServicerContext
    ) -> FriendConfirmReply:
        # request.action - Accepted / Rejected / Ignored
        link = request.link
        request_id = link.request_id
        address_id = link.address_id

        if (action := request.action) is ACCEPTED:
            reply: Optional[FriendConfirmReply] = None
            session_id = request.session_id
            while not context.cancelled() and reply is None:
                try:
                    _, delay = await self.create_friend(
                        request_id=request_id,
                        address_id=address_id,
                        session_id=session_id,
                        timeout=context.time_remaining(),
                    )
                    logger.warning(f"Confirm transaction consumes: {delay}")
                except TransactionFailed as exc:
                    if (status := exc.args[0]) is DB_INFO_DUP_ENTRY:
                        logger.info(
                            "conflict session_id in `create_friend`, attempt to retry."
                        )
                        continue
                    elif status is DB_TIMEOUT_HANDLING:
                        logger.exception(
                            "timeout when waiting db_service to return a result",
                            exc_info=False,
                        )
                        reply = FriendConfirmReply(status=FRIEND_TIMEOUT)
                    else:
                        reply = FriendConfirmReply(status=FRIEND_FAILED)
                else:
                    reply = (
                        FriendConfirmReply(status=FRIEND_SUCCESS)
                        if session_id is not None
                        else FriendConfirmReply(status=FRIEND_TIMEOUT)
                    )

            return reply if not context.cancelled() else None

        elif action is REJECTED:
            meth = self.reject_friend_request
        elif action is IGNORED:
            meth = self.ignore_friend_request
        else:
            raise NotImplementedError(f"not support action: {action}")

        result, _ = await meth(
            request_id=request_id,
            address_id=address_id,
            timeout=context.time_remaining(),
        )
        if result is None:
            return FriendConfirmReply(status=FRIEND_TIMEOUT)

        result = cast(ExecutionResult, result)
        if (status := result.status) is DB_SUCCESS:
            reply = FriendConfirmReply(status=FRIEND_SUCCESS)
        elif status is DB_TIMEOUT_HANDLING:
            reply = FriendConfirmReply(status=FRIEND_TIMEOUT)
        else:
            reply = FriendConfirmReply(status=FRIEND_FAILED)

        if not context.cancelled():
            return reply

    async def GetFriendList(
        self, request: FriendListRequest, context: AioServicerContext
    ) -> FriendListReply:
        result, delay = await self.get_friends(
            owner_id=request.seq,
            timeout=context.time_remaining(),
        )
        if result is None:
            return FriendListReply(status=FRIEND_FAILED)

        logger.warning(f"Get Friend List consumes: {delay}")
        result = cast(ExecutionResult, result)
        status = result.status
        if status is DB_SUCCESS:
            query_data = result.data
            friends = (
                [
                    FriendDetailedInfo(
                        session_id=record["session_id"],
                        seq=record["seq"],
                        uid=record["uid"].bytes,
                        username=record["username"],
                        email=record["email"],
                        remark=record["remarks"],
                    )
                    for record in query_data
                ]
                if query_data
                else None
            )
            reply = FriendListReply(status=FRIEND_SUCCESS, friends=friends)
        elif status is DB_TIMEOUT_HANDLING:
            logger.info("timeout when waiting db_service to return a result")
            reply = FriendListReply(status=FRIEND_TIMEOUT)
        else:
            logger.info(f"{result.msg}")
            reply = FriendListReply(status=FRIEND_FAILED)

        if not context.cancelled():
            return reply
