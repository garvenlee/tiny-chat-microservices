from . import msg_data_pb2 as _msg_data_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import (
    ClassVar as _ClassVar,
    Iterable as _Iterable,
    Mapping as _Mapping,
    Optional as _Optional,
    Union as _Union,
)

DESCRIPTOR: _descriptor.FileDescriptor

class CassMessageStatusCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    CASS_MSG_SUCCESS: _ClassVar[CassMessageStatusCode]
    CASS_MSG_TIMEOUT: _ClassVar[CassMessageStatusCode]
    CASS_MSG_FAILED: _ClassVar[CassMessageStatusCode]

CASS_MSG_SUCCESS: CassMessageStatusCode
CASS_MSG_TIMEOUT: CassMessageStatusCode
CASS_MSG_FAILED: CassMessageStatusCode

class CassMsgRequest(_message.Message):
    __slots__ = ["message_data", "message_id", "delivery_id"]
    MESSAGE_DATA_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    DELIVERY_ID_FIELD_NUMBER: _ClassVar[int]
    message_data: _msg_data_pb2.MsgData
    message_id: int
    delivery_id: int
    def __init__(
        self,
        message_data: _Optional[_Union[_msg_data_pb2.MsgData, _Mapping]] = ...,
        message_id: _Optional[int] = ...,
        delivery_id: _Optional[int] = ...,
    ) -> None: ...

class CassMsgReply(_message.Message):
    __slots__ = ["code"]
    CODE_FIELD_NUMBER: _ClassVar[int]
    code: CassMessageStatusCode
    def __init__(
        self, code: _Optional[_Union[CassMessageStatusCode, str]] = ...
    ) -> None: ...

class CassInboxRequest(_message.Message):
    __slots__ = ["uid", "last_max_msg_id"]
    UID_FIELD_NUMBER: _ClassVar[int]
    LAST_MAX_MSG_ID_FIELD_NUMBER: _ClassVar[int]
    uid: int
    last_max_msg_id: int
    def __init__(
        self, uid: _Optional[int] = ..., last_max_msg_id: _Optional[int] = ...
    ) -> None: ...

class CassInboxReply(_message.Message):
    __slots__ = ["code", "messages"]
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGES_FIELD_NUMBER: _ClassVar[int]
    code: CassMessageStatusCode
    messages: _containers.RepeatedCompositeFieldContainer[_msg_data_pb2.ServerMsgData]
    def __init__(
        self,
        code: _Optional[_Union[CassMessageStatusCode, str]] = ...,
        messages: _Optional[
            _Iterable[_Union[_msg_data_pb2.ServerMsgData, _Mapping]]
        ] = ...,
    ) -> None: ...

class CassSessionRequest(_message.Message):
    __slots__ = ["session_ids"]
    SESSION_IDS_FIELD_NUMBER: _ClassVar[int]
    session_ids: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, session_ids: _Optional[_Iterable[int]] = ...) -> None: ...

class CassSessionReply(_message.Message):
    __slots__ = ["session_id", "token", "messages"]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    MESSAGES_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    token: bytes
    messages: _containers.RepeatedCompositeFieldContainer[_msg_data_pb2.ServerMsgData]
    def __init__(
        self,
        session_id: _Optional[int] = ...,
        token: _Optional[bytes] = ...,
        messages: _Optional[
            _Iterable[_Union[_msg_data_pb2.ServerMsgData, _Mapping]]
        ] = ...,
    ) -> None: ...
