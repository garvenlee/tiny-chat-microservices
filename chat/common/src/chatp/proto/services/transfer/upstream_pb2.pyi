from . import msg_data_pb2 as _msg_data_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import (
    ClassVar as _ClassVar,
    Mapping as _Mapping,
    Optional as _Optional,
    Union as _Union,
)

DESCRIPTOR: _descriptor.FileDescriptor

class UpstreamTransferStatusCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    UPSTREAM_DELIVERY_SUCCESS: _ClassVar[UpstreamTransferStatusCode]
    UPSTREAM_DELIVERY_TIMEOUT: _ClassVar[UpstreamTransferStatusCode]
    UPSTREAM_DELIVERY_FAILED: _ClassVar[UpstreamTransferStatusCode]

UPSTREAM_DELIVERY_SUCCESS: UpstreamTransferStatusCode
UPSTREAM_DELIVERY_TIMEOUT: UpstreamTransferStatusCode
UPSTREAM_DELIVERY_FAILED: UpstreamTransferStatusCode

class DeliverUpMsgRequest(_message.Message):
    __slots__ = ["message_data"]
    MESSAGE_DATA_FIELD_NUMBER: _ClassVar[int]
    message_data: _msg_data_pb2.ClientMsgData
    def __init__(
        self,
        message_data: _Optional[_Union[_msg_data_pb2.ClientMsgData, _Mapping]] = ...,
    ) -> None: ...

class DeliverUpMsgReply(_message.Message):
    __slots__ = ["code", "message_id"]
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    code: UpstreamTransferStatusCode
    message_id: int
    def __init__(
        self,
        code: _Optional[_Union[UpstreamTransferStatusCode, str]] = ...,
        message_id: _Optional[int] = ...,
    ) -> None: ...
