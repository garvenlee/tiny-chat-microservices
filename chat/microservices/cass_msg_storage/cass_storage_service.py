from time import time, monotonic
from typing import Optional, AsyncGenerator
from logging import getLogger
from dataclasses import dataclass
from collections import defaultdict, deque

from cachetools import LRUCache
from asyncio import (
    shield,
    sleep,
    get_running_loop,
    Event as AsyncIOEvent,
    Lock as AsyncIOLock,
    Task,
    CancelledError,
)
from acsylla.base import Result
from grpc.aio import ServicerContext as AioServicerContext

from chatp.redis.client import RedisClient
from chatp.redis.model import REDIS_SUCCESS, REDIS_TIMEOUT
from chatp.proto.services.transfer.msg_data_pb2 import MsgData, ServerMsgData
from chatp.proto.services.transfer.cass_storage_pb2 import (
    CassMsgRequest,
    CassMsgReply,
    CassInboxRequest,
    CassInboxReply,
    CassSessionRequest,
    CassSessionReply,
    CASS_MSG_SUCCESS,
    CASS_MSG_TIMEOUT,
    CASS_MSG_FAILED,
)
from chatp.proto.services.transfer.cass_storage_pb2_grpc import (
    CassStorageServicer as ProtoServicer,
)

from db_service import MessageExecutor

CHATAPP_EPOCH = 1701180600000
MESSAGE_COUNT_ONE_BUCKET = 1_000_000  # 100B one message, 100M / 100B = 1M
DAYS_ONE_BUCKET = 1000 * 60 * 60 * 24 * 10  # 10day in ms

logger = getLogger("CassStorageService")
logger.setLevel(10)


def make_bucket(snowflake: Optional[int]):
    if snowflake is None:
        timestamp = int(time() * 1000) - CHATAPP_EPOCH
    else:
        timestamp = snowflake >> 22  # ms timestamp
    return int(timestamp / DAYS_ONE_BUCKET)


def make_buckets(start_id, end_id=None):
    return range(make_bucket(start_id), make_bucket(end_id) + 1)


@dataclass
class BucketCacheLine:
    bucket: int
    curr_val: int
    end_val: int
    redis_key: str
    lock: AsyncIOLock

    @property
    def ready(self):
        return self.end_val > 0

    @classmethod
    def create(cls, redis_key: str):
        return cls(-1, -1, -1, redis_key, AsyncIOLock())


@dataclass
class WriteOperation:
    task: Task
    deadline_at: float
    event: AsyncIOEvent

    @property
    def inflight(self):
        return not self.task.done()

    @property
    def still_valid(self):
        return monotonic() < self.deadline_at


class CassStorageService(ProtoServicer):
    def __init__(self, message_executor: MessageExecutor, redis_client: RedisClient):
        self.write_session = message_executor.write_session
        self.write_inbox = message_executor.write_inbox
        self.read_inbox = message_executor.read_inbox
        self.read_session = message_executor.read_session

        # self.write_cache: dict[int, WriteOperation] = {}  # message_id : WriteOperation
        self.bucket_cache: LRUCache[int, BucketCacheLine] = LRUCache(2**14)

        self.redis_client = redis_client
        self.redis_incr = redis_client.redis_incr

        loop = get_running_loop()
        self.task_factory = loop.create_task

        self.shutdown = False

    async def cal_bucket_val(self, channel_id: int) -> int:
        bucket_cache = self.bucket_cache
        if (line := bucket_cache.get(channel_id)) is None:
            line = BucketCacheLine.create(
                f"chatp:cass_storage:p2p:msg_count:{channel_id}"
            )
            bucket_cache[channel_id] = line

        if lock_acquired := not line.ready:
            await line.lock.acquire()

        if (end_val := line.end_val) > 0:
            curr_val = line.curr_val
            curr_val += 1
            if curr_val < end_val:
                line.curr_val = curr_val
                if lock_acquired:
                    line.lock.release()
                return line.bucket

            # safe consideration: many write at the same time but needs a new bucket
            if not lock_acquired:
                await line.lock.acquire()

        # TODO If there are multiple redis instances, then needs lock
        end_val, status = await self.redis_incr(line.redis_key, 100, timeout=1)
        line.lock.release()
        if status is REDIS_SUCCESS:
            line.end_val = end_val
            line.curr_val = curr_val = end_val - 100  # [0 - 99] ... [1M - 101, 1M - 1]
            line.bucket = bucket = curr_val // MESSAGE_COUNT_ONE_BUCKET
            return bucket  # 0, 1, 2 ...
        elif status is REDIS_TIMEOUT:
            # TODO If timeout, but redis already executes incr command.
            # thought RedisClient implements rollback, but it's not 100% safe
            return -1
        else:
            return -2

    async def WriteToSession(
        self, request: CassMsgRequest, context: AioServicerContext
    ) -> CassMsgReply:
        # First, decide the bucket  TODO add type here
        msg_data = request.message_data
        channel_id = msg_data.session_id
        bucket = await self.cal_bucket_val(channel_id)
        if bucket >= 0:
            # Second, attempt to write cassandra
            try:
                message_id = request.message_id
                task = self.task_factory(
                    self.write_session(
                        channel_id=channel_id,
                        bucket=bucket,
                        message_id=message_id,
                        sender_seq=request.delivery_id,
                        sender_id=msg_data.sender_id,
                        receiver_id=msg_data.receiver_id,
                        content=msg_data.text,
                    )
                )
                await shield(task)
            except CancelledError:  # for grpc timeout
                self.bucket_cache[channel_id].curr_val -= 1  # rollback
                if self.shutdown:
                    task.cancel()
                    logger.warning("RPC Call was cancelled due to server down")
                else:
                    logger.warning("RPC Call was cancelled due to deadline")
            except BaseException as exc:
                self.bucket_cache[channel_id].curr_val -= 1  # rollback
                logger.exception(
                    "Found exception in cassandra write: %s", exc, exc_info=exc
                )
                reply = CassMsgReply(code=CASS_MSG_FAILED)
            else:
                reply = CassMsgReply(code=CASS_MSG_SUCCESS)
                # Third, collect the count, when to update message_count?

            if not context.cancelled():
                return reply
            else:
                self.bucket_cache[channel_id].curr_val -= 1  # rollback
        elif bucket == -1:
            return CassMsgReply(code=CASS_MSG_TIMEOUT)
        elif bucket == -2:
            return CassMsgReply(code=CASS_MSG_FAILED)

    # TODO No bucket in Inbox, How to limit the number of messages in one Inbox?
    # After user pull his/her Inbox and saved messages in the local storage, user can send
    # one PullAck via websocket to notify the CassStorage to clear unnecessary messages in Inbox.
    # When to send this PullAck? At the time user finds the size of inbox is too large.
    async def WriteToInbox(
        self, request: CassMsgRequest, context: AioServicerContext
    ) -> CassMsgReply:
        try:
            # TODO here, not only write to receiver's inbox, but also write to sender's inbox
            # in order to implement multi-terminal sync
            msg_data = request.message_data
            message_id = request.message_id
            task = self.task_factory(
                self.write_inbox(
                    channel_id=msg_data.session_id,
                    message_id=message_id,
                    sender_seq=request.delivery_id,
                    sender_id=msg_data.sender_id,
                    receiver_id=msg_data.receiver_id,
                    content=msg_data.text,
                )
            )
            await shield(task)
        except CancelledError:
            if self.shutdown:
                task.cancel()
                logger.warning("WriteToBox GrpcCall was cancelled due to server down")
            else:
                logger.warning("WriteToBox GrpcCall was cancelled due to deadline")
        except BaseException as exc:
            logger.exception(
                "Found exception in cassandra write: %s", exc, exc_info=exc
            )
            reply = CassMsgReply(code=CASS_MSG_FAILED)
        else:
            reply = CassMsgReply(code=CASS_MSG_SUCCESS)

        if not context.cancelled():
            return reply

    async def ReadInbox(
        self, request: CassInboxRequest, context: AioServicerContext
    ) -> CassInboxReply:
        try:
            address_id = request.uid
            task = self.task_factory(
                self.read_inbox(
                    receiver_id=address_id,
                    max_recv_msg_id=request.last_max_msg_id,
                )
            )
            result: Result = await shield(
                task
            )  # TODO evaluate the benefit of shield in Read
        except CancelledError:
            if self.shutdown:
                task.cancel()
                logger.warning("ReadInbox GrpcCall was cancelled due to server down")
            else:
                logger.warning("ReadInbox GrpcCall was cancelled due to deadline")
        except BaseException as exc:  # s.t. ReadTimeout
            logger.exception(
                "Found exception in cassandra reade: %s", exc, exc_info=exc
            )
            reply = CassInboxReply(code=CASS_MSG_FAILED)
        else:
            count = result.count()
            if count == 0:
                return CassInboxReply(code=CASS_MSG_SUCCESS)

            logger.info("ReadInbox got %s messages for %s", count, address_id)
            # resize 5 times, list items reach 32
            messages = [] if count <= 32 else deque()
            messages_append = messages.append

            # TODO Check: put message filter here but not in ReadModel, decrease the data transmission
            handled = defaultdict(set)
            for row in result:
                row_data = row.as_dict()
                sender_id, sender_seq = row_data["sender_id"], row_data["sender_seq"]
                if sender_seq not in (bucket := handled[sender_id]):
                    bucket.add(sender_seq)
                    msg_data = MsgData(
                        session_id=row_data["channel_id"],
                        sender_id=row_data["sender_id"],
                        text=row_data["content"],
                    )
                    messages_append(
                        ServerMsgData(data=msg_data, message_id=row_data["message_id"])
                    )
                else:
                    logger.warning("Found duplicate message in message-stream")
            reply = CassInboxReply(code=CASS_MSG_SUCCESS, messages=messages)

        if not context.cancelled():
            return reply

    async def ReadSession(
        self, request: CassSessionRequest, context: AioServicerContext
    ) -> AsyncGenerator[CassSessionReply, None]:
        session_ids = deque(request.session_ids)
        session_id = session_ids.popleft()
        result: Result = await self.read_session(session_id=session_id)

        create_task = get_running_loop().create_task
        while True:
            if session_ids:
                session_id = session_ids.popleft()
                next_page = create_task(self.read_session(session_id=session_id))
                await sleep(0)
            else:
                next_page = None

            token = result.page_state() if result.has_more_pages() else None
            messages = deque()
            messages_append = messages.append
            for row in result:
                row_data = row.as_dict()
                msg_data = MsgData(
                    sender_id=row_data["sender_id"], text=row_data["content"]
                )
                messages_append(
                    ServerMsgData(data=msg_data, message_id=row_data["message_id"])
                )

            yield CassSessionReply(token=token, messages=messages)

            if next_page is not None:
                result = await next_page
            else:
                break
