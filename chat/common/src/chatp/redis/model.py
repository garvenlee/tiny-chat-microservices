from time import monotonic
from enum import IntEnum
from typing import Optional
from dataclasses import dataclass

from asyncio import Future, Task
from google.protobuf import message


class RedisTaskType(IntEnum):
    GET = 0
    BATCH_GET = 2
    MGET = 4
    HLEN = 6
    HGET = 8
    HGETALL = 10
    IP_LIMITER = 12
    TOKEN_LIMITER = 14

    SET = 1
    BATCH_SET = 3
    SETNX = 5
    MSET = 7
    HSET = 9
    HDEL = 11
    INCR = 13
    LPUSH = 15
    RPUSH = 17
    DELETE = 19
    BATCH_DELETE = 21
    UNLINK = 23


TASK_BATCH_GET = RedisTaskType.BATCH_GET
TASK_BATCH_SET = RedisTaskType.BATCH_SET
TASK_BATCH_DELETE = RedisTaskType.BATCH_DELETE

TASK_GET = RedisTaskType.GET
TASK_SET = RedisTaskType.SET
TASK_SETNX = RedisTaskType.SETNX
TASK_MGET = RedisTaskType.MGET
TASK_MSET = RedisTaskType.MSET

TASK_HLEN = RedisTaskType.HLEN
TASK_HGET = RedisTaskType.HGET
TASK_HSET = RedisTaskType.HSET
TASK_HDEL = RedisTaskType.HDEL
TASK_HGETALL = RedisTaskType.HGETALL

TASK_INCR = RedisTaskType.INCR
TASK_LPUSH = RedisTaskType.LPUSH
TASK_RPUSH = RedisTaskType.RPUSH
TASK_DELETE = RedisTaskType.DELETE
TASK_UNLINK = RedisTaskType.UNLINK
TASK_IP_LIMITER = RedisTaskType.IP_LIMITER
TASK_TOKEN_LIMITER = RedisTaskType.TOKEN_LIMITER


class RedisOperationType(IntEnum):
    READ = 0
    WRITE = 1


OPERATION_READ = RedisOperationType.READ
OPERATION_WRITE = RedisOperationType.WRITE


@dataclass
class RedisTask:
    task_type: RedisTaskType
    task_data: message.Message
    waiter: Optional[Future] = None


@dataclass
class RedisBatchTask:
    task_type: RedisTaskType
    task_data: tuple[message.Message]
    waiter: Future


class TaskStatus(IntEnum):
    INITIALIZED = 0
    READY = 1
    RUNNING = 2
    IDLE = 3


TASK_INITIALIZED = TaskStatus.INITIALIZED
TASK_READY = TaskStatus.READY
TASK_IDLE = TaskStatus.IDLE
TASK_RUNNING = TaskStatus.RUNNING


class ResponseStatus(IntEnum):
    REDIS_SUCCESS = 0
    REDIS_FAILED = 1
    REDIS_TIMEOUT = 2


class RatelimiterStatus(IntEnum):
    ALLOWED = 0
    REJECTED = 1
    BLOCKED = 2


REDIS_SUCCESS = ResponseStatus.REDIS_SUCCESS
REDIS_FAILED = ResponseStatus.REDIS_FAILED
REDIS_TIMEOUT = ResponseStatus.REDIS_TIMEOUT
RATE_ALLOWED = RatelimiterStatus.ALLOWED
RATE_REJECTED = RatelimiterStatus.REJECTED
RATE_BLOCKED = RatelimiterStatus.BLOCKED


class TaskConsumer:
    __slots__ = "status", "last_state", "task", "rebalance_trap"

    def __init__(self, task: Optional[Task] = None):
        self.status = TASK_INITIALIZED
        self.last_state = monotonic()  # last interaction timestamp
        self.task = task
        self.rebalance_trap = False
