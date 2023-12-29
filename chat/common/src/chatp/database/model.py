from enum import IntEnum
from typing import Optional, NamedTuple, Any


class BatchType(IntEnum):
    UNLOGGED = 0
    LOGGED = 1
    COUNTER = 2


class CachedStatement(NamedTuple):
    cql: str
    prepared: Any
    statement: Any


# panic: need to retry
# failed: cannot retry
# info: a hint to user about dup etc
class ExecutionStatus(IntEnum):
    SUCCESS = 0
    # FAILED val must be greater than 0
    FAILED = 1

    # PANIC: second bit must be 1
    PANIC = 2
    # INFO: third bit must be 1
    INFO = 4

    PANIC_IO_ERROR = 3
    PANIC_SEQ_NUM_WRONG = 10
    PANIC_INTERFACE = 11

    INFO_DUP_ENTRY = 5
    TIMEOUT_PENDING = 8
    TIMEOUT_HANDLING = 9


class ExecutionResult(NamedTuple):
    status: ExecutionStatus
    msg: str
    data: Optional[Any] = None


DB_SUCCESS = ExecutionStatus.SUCCESS
DB_FAILED = ExecutionStatus.FAILED
DB_PANIC = ExecutionStatus.PANIC
DB_INFO = ExecutionStatus.INFO

DB_PANIC_IO_ERROR = ExecutionStatus.PANIC_IO_ERROR
DB_PANIC_SEQ_NUM_WRONG = ExecutionStatus.PANIC_SEQ_NUM_WRONG
DB_PANIC_INTERFACE = ExecutionStatus.PANIC_INTERFACE
DB_INFO_DUP_ENTRY = ExecutionStatus.INFO_DUP_ENTRY
DB_TIMEOUT_PENDING = ExecutionStatus.TIMEOUT_PENDING
DB_TIMEOUT_HANDLING = ExecutionStatus.TIMEOUT_HANDLING
