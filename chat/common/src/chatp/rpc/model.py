from enum import IntEnum
from typing import NamedTuple, Optional

from google.protobuf.message import Message


class ConnState(IntEnum):
    CONNECTED = 1
    CONNECTING = 2
    DISCONNECT = 3
    FAILED = 4


class GrpcStatus(IntEnum):
    SUCCESS = 0
    FAILED = 1
    TIMEOUT = 2

    ARGS_MISMATCH = 4
    ARGS_TYPE_ERROR = 5
    INTERFACE_ERROR = 6


GRPC_SUCCESS = GrpcStatus.SUCCESS
GRPC_FAILED = GrpcStatus.FAILED
GRPC_TIMEOUT = GrpcStatus.TIMEOUT
GRPC_ARGS_MISMATCH = GrpcStatus.ARGS_MISMATCH
GRPC_ARGS_TYPE_ERROR = GrpcStatus.ARGS_TYPE_ERROR
GRPC_INTERFACE_ERROR = GrpcStatus.INTERFACE_ERROR


class CallResult(NamedTuple):
    status: GrpcStatus
    info: Optional[str | BaseException] = None
    data: Optional[Message] = None
