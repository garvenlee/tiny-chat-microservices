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

class PubEventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    PUSH_FRIEND_REQUEST: _ClassVar[PubEventType]
    PUSH_FRIEND_CONFIRM: _ClassVar[PubEventType]
    PUSH_FRIEND_SESSION: _ClassVar[PubEventType]
    PUSH_USER_KICKED_OFF: _ClassVar[PubEventType]
    PUSH_USER_MESSAGE: _ClassVar[PubEventType]
    PUSH_USER_EVENT: _ClassVar[PubEventType]
    ACK_ACTION: _ClassVar[PubEventType]
    ACK_FRIEND_REQUEST: _ClassVar[PubEventType]
    ACK_FRIEND_CONFIRM: _ClassVar[PubEventType]
    ACK_FRIEND_SESSION: _ClassVar[PubEventType]
    ACK_USER_MESSAGE: _ClassVar[PubEventType]
    ACK_USER_EVENT: _ClassVar[PubEventType]

class PubStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    PUSH_SUCCESS: _ClassVar[PubStatus]
    PUSH_TIMEOUT: _ClassVar[PubStatus]
    PUSH_FAILED: _ClassVar[PubStatus]
    PUSH_OFFLINE: _ClassVar[PubStatus]

PUSH_FRIEND_REQUEST: PubEventType
PUSH_FRIEND_CONFIRM: PubEventType
PUSH_FRIEND_SESSION: PubEventType
PUSH_USER_KICKED_OFF: PubEventType
PUSH_USER_MESSAGE: PubEventType
PUSH_USER_EVENT: PubEventType
ACK_ACTION: PubEventType
ACK_FRIEND_REQUEST: PubEventType
ACK_FRIEND_CONFIRM: PubEventType
ACK_FRIEND_SESSION: PubEventType
ACK_USER_MESSAGE: PubEventType
ACK_USER_EVENT: PubEventType
PUSH_SUCCESS: PubStatus
PUSH_TIMEOUT: PubStatus
PUSH_FAILED: PubStatus
PUSH_OFFLINE: PubStatus

class MessageLog(_message.Message):
    __slots__ = ["evt_tp", "channel_number", "delivery_id"]
    EVT_TP_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_NUMBER_FIELD_NUMBER: _ClassVar[int]
    DELIVERY_ID_FIELD_NUMBER: _ClassVar[int]
    evt_tp: PubEventType
    channel_number: int
    delivery_id: int
    def __init__(
        self,
        evt_tp: _Optional[_Union[PubEventType, str]] = ...,
        channel_number: _Optional[int] = ...,
        delivery_id: _Optional[int] = ...,
    ) -> None: ...

class PubEventToUser(_message.Message):
    __slots__ = ["log", "evt_data"]
    LOG_FIELD_NUMBER: _ClassVar[int]
    EVT_DATA_FIELD_NUMBER: _ClassVar[int]
    log: MessageLog
    evt_data: bytes
    def __init__(
        self,
        log: _Optional[_Union[MessageLog, _Mapping]] = ...,
        evt_data: _Optional[bytes] = ...,
    ) -> None: ...

class PubEventAckFromUser(_message.Message):
    __slots__ = ["logs"]
    LOGS_FIELD_NUMBER: _ClassVar[int]
    logs: _containers.RepeatedCompositeFieldContainer[MessageLog]
    def __init__(
        self, logs: _Optional[_Iterable[_Union[MessageLog, _Mapping]]] = ...
    ) -> None: ...

class PubEventFromUser(_message.Message):
    __slots__ = ["evt_tp", "payload"]
    EVT_TP_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    evt_tp: PubEventType
    payload: bytes
    def __init__(
        self,
        evt_tp: _Optional[_Union[PubEventType, str]] = ...,
        payload: _Optional[bytes] = ...,
    ) -> None: ...

class PubEventAckToUser(_message.Message):
    __slots__ = ["acked", "message_id"]
    ACKED_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_ID_FIELD_NUMBER: _ClassVar[int]
    acked: bool
    message_id: int
    def __init__(self, acked: bool = ..., message_id: _Optional[int] = ...) -> None: ...

class PubEventToGateway(_message.Message):
    __slots__ = ["evt_tp", "delivery_id", "evt_data"]
    EVT_TP_FIELD_NUMBER: _ClassVar[int]
    DELIVERY_ID_FIELD_NUMBER: _ClassVar[int]
    EVT_DATA_FIELD_NUMBER: _ClassVar[int]
    evt_tp: PubEventType
    delivery_id: int
    evt_data: bytes
    def __init__(
        self,
        evt_tp: _Optional[_Union[PubEventType, str]] = ...,
        delivery_id: _Optional[int] = ...,
        evt_data: _Optional[bytes] = ...,
    ) -> None: ...

class PubEventAckFromGateway(_message.Message):
    __slots__ = ["start_id", "end_id"]
    START_ID_FIELD_NUMBER: _ClassVar[int]
    END_ID_FIELD_NUMBER: _ClassVar[int]
    start_id: int
    end_id: int
    def __init__(
        self, start_id: _Optional[int] = ..., end_id: _Optional[int] = ...
    ) -> None: ...

class ConsumerFeedback(_message.Message):
    __slots__ = ["status", "confirm"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CONFIRM_FIELD_NUMBER: _ClassVar[int]
    status: PubStatus
    confirm: PubEventAckFromGateway
    def __init__(
        self,
        status: _Optional[_Union[PubStatus, str]] = ...,
        confirm: _Optional[_Union[PubEventAckFromGateway, _Mapping]] = ...,
    ) -> None: ...

class ControlMessageData(_message.Message):
    __slots__ = []
    def __init__(self) -> None: ...

class ControlMessageAck(_message.Message):
    __slots__ = []
    def __init__(self) -> None: ...

class PubUserMessage(_message.Message):
    __slots__ = ["address_id", "payload"]
    ADDRESS_ID_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    address_id: int
    payload: bytes
    def __init__(
        self, address_id: _Optional[int] = ..., payload: _Optional[bytes] = ...
    ) -> None: ...

class PubNotificationHeader(_message.Message):
    __slots__ = ["data_type", "address_id"]
    DATA_TYPE_FIELD_NUMBER: _ClassVar[int]
    ADDRESS_ID_FIELD_NUMBER: _ClassVar[int]
    data_type: PubEventType
    address_id: int
    def __init__(
        self,
        data_type: _Optional[_Union[PubEventType, str]] = ...,
        address_id: _Optional[int] = ...,
    ) -> None: ...

class PubNotification(_message.Message):
    __slots__ = ["header", "payload"]
    HEADER_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    header: PubNotificationHeader
    payload: bytes
    def __init__(
        self,
        header: _Optional[_Union[PubNotificationHeader, _Mapping]] = ...,
        payload: _Optional[bytes] = ...,
    ) -> None: ...

class PubNotificationAck(_message.Message):
    __slots__ = ["status"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: PubStatus
    def __init__(self, status: _Optional[_Union[PubStatus, str]] = ...) -> None: ...
