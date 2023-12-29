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

class DLQMsgAction(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    DLQ_ALL: _ClassVar[DLQMsgAction]
    DLQ_SESSION_ONLY: _ClassVar[DLQMsgAction]
    DLQ_INBOX_ONLY: _ClassVar[DLQMsgAction]

DLQ_ALL: DLQMsgAction
DLQ_SESSION_ONLY: DLQMsgAction
DLQ_INBOX_ONLY: DLQMsgAction

class MsgData(_message.Message):
    __slots__ = ["session_id", "sender_id", "receiver_id", "text"]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    SENDER_ID_FIELD_NUMBER: _ClassVar[int]
    RECEIVER_ID_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    sender_id: int
    receiver_id: int
    text: str
    def __init__(
        self,
        session_id: _Optional[int] = ...,
        sender_id: _Optional[int] = ...,
        receiver_id: _Optional[int] = ...,
        text: _Optional[str] = ...,
    ) -> None: ...

class ClientMsgData(_message.Message):
    __slots__ = ["data", "delivery_id"]
    DATA_FIELD_NUMBER: _ClassVar[int]
    DELIVERY_ID_FIELD_NUMBER: _ClassVar[int]
    data: MsgData
    delivery_id: int
    def __init__(
        self,
        data: _Optional[_Union[MsgData, _Mapping]] = ...,
        delivery_id: _Optional[int] = ...,
    ) -> None: ...

class ServerMsgData(_message.Message):
    __slots__ = ["data", "message_id"]
    DATA_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    data: MsgData
    message_id: int
    def __init__(
        self,
        data: _Optional[_Union[MsgData, _Mapping]] = ...,
        message_id: _Optional[int] = ...,
    ) -> None: ...

class RStreamMsgData(_message.Message):
    __slots__ = ["data", "delivery_id", "message_id"]
    DATA_FIELD_NUMBER: _ClassVar[int]
    DELIVERY_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    data: MsgData
    delivery_id: int
    message_id: int
    def __init__(
        self,
        data: _Optional[_Union[MsgData, _Mapping]] = ...,
        delivery_id: _Optional[int] = ...,
        message_id: _Optional[int] = ...,
    ) -> None: ...

class DLQMsgData(_message.Message):
    __slots__ = ["action", "data"]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    action: DLQMsgAction
    data: RStreamMsgData
    def __init__(
        self,
        action: _Optional[_Union[DLQMsgAction, str]] = ...,
        data: _Optional[_Union[RStreamMsgData, _Mapping]] = ...,
    ) -> None: ...
