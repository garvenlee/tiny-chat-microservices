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

class ReadModelEventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    READ_MODEL_SINGLE_CHAT: _ClassVar[ReadModelEventType]
    READ_MODEL_GROUP_CHAT: _ClassVar[ReadModelEventType]

class DeliverReadEventStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    READ_MODEL_SUCCESS: _ClassVar[DeliverReadEventStatus]
    READ_MODEL_TIMEOUT: _ClassVar[DeliverReadEventStatus]
    READ_MODEL_FAILED: _ClassVar[DeliverReadEventStatus]

READ_MODEL_SINGLE_CHAT: ReadModelEventType
READ_MODEL_GROUP_CHAT: ReadModelEventType
READ_MODEL_SUCCESS: DeliverReadEventStatus
READ_MODEL_TIMEOUT: DeliverReadEventStatus
READ_MODEL_FAILED: DeliverReadEventStatus

class ReadModelEvent(_message.Message):
    __slots__ = ["event_tp", "delivery_id", "message"]
    EVENT_TP_FIELD_NUMBER: _ClassVar[int]
    DELIVERY_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    event_tp: ReadModelEventType
    delivery_id: int
    message: _msg_data_pb2.ServerMsgData
    def __init__(
        self,
        event_tp: _Optional[_Union[ReadModelEventType, str]] = ...,
        delivery_id: _Optional[int] = ...,
        message: _Optional[_Union[_msg_data_pb2.ServerMsgData, _Mapping]] = ...,
    ) -> None: ...

class DeliverReadEventReply(_message.Message):
    __slots__ = ["status"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: DeliverReadEventStatus
    def __init__(
        self, status: _Optional[_Union[DeliverReadEventStatus, str]] = ...
    ) -> None: ...

class PullInboxRequest(_message.Message):
    __slots__ = ["uid", "received_max_msg_id"]
    UID_FIELD_NUMBER: _ClassVar[int]
    RECEIVED_MAX_MSG_ID_FIELD_NUMBER: _ClassVar[int]
    uid: int
    received_max_msg_id: int
    def __init__(
        self, uid: _Optional[int] = ..., received_max_msg_id: _Optional[int] = ...
    ) -> None: ...

class PullInboxReply(_message.Message):
    __slots__ = ["status", "messages"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    MESSAGES_FIELD_NUMBER: _ClassVar[int]
    status: DeliverReadEventStatus
    messages: _containers.RepeatedCompositeFieldContainer[_msg_data_pb2.ServerMsgData]
    def __init__(
        self,
        status: _Optional[_Union[DeliverReadEventStatus, str]] = ...,
        messages: _Optional[
            _Iterable[_Union[_msg_data_pb2.ServerMsgData, _Mapping]]
        ] = ...,
    ) -> None: ...
