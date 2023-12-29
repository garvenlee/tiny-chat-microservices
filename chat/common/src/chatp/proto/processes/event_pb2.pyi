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

class EventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    SERVICE_CHANGE: _ClassVar[EventType]
    LOAD_HINT: _ClassVar[EventType]
    USER_EVENT: _ClassVar[EventType]

class ServiceEventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    SERVICE_ONLINE: _ClassVar[ServiceEventType]
    SERVICE_OFFLINE: _ClassVar[ServiceEventType]

SERVICE_CHANGE: EventType
LOAD_HINT: EventType
USER_EVENT: EventType
SERVICE_ONLINE: ServiceEventType
SERVICE_OFFLINE: ServiceEventType

class ServiceEvent(_message.Message):
    __slots__ = ["srv_tp", "srv_name", "srv_addr", "platform_id"]
    SRV_TP_FIELD_NUMBER: _ClassVar[int]
    SRV_NAME_FIELD_NUMBER: _ClassVar[int]
    SRV_ADDR_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_ID_FIELD_NUMBER: _ClassVar[int]
    srv_tp: ServiceEventType
    srv_name: str
    srv_addr: str
    platform_id: str
    def __init__(
        self,
        srv_tp: _Optional[_Union[ServiceEventType, str]] = ...,
        srv_name: _Optional[str] = ...,
        srv_addr: _Optional[str] = ...,
        platform_id: _Optional[str] = ...,
    ) -> None: ...

class LoadHintEvent(_message.Message):
    __slots__ = ["srv_name", "srv_addr", "weight"]
    SRV_NAME_FIELD_NUMBER: _ClassVar[int]
    SRV_ADDR_FIELD_NUMBER: _ClassVar[int]
    WEIGHT_FIELD_NUMBER: _ClassVar[int]
    srv_name: str
    srv_addr: str
    weight: bytes
    def __init__(
        self,
        srv_name: _Optional[str] = ...,
        srv_addr: _Optional[str] = ...,
        weight: _Optional[bytes] = ...,
    ) -> None: ...

class Event(_message.Message):
    __slots__ = ["evt_tp", "srv_evt", "load_evt", "user_evt"]
    EVT_TP_FIELD_NUMBER: _ClassVar[int]
    SRV_EVT_FIELD_NUMBER: _ClassVar[int]
    LOAD_EVT_FIELD_NUMBER: _ClassVar[int]
    USER_EVT_FIELD_NUMBER: _ClassVar[int]
    evt_tp: EventType
    srv_evt: ServiceEvent
    load_evt: LoadHintEvent
    user_evt: bytes
    def __init__(
        self,
        evt_tp: _Optional[_Union[EventType, str]] = ...,
        srv_evt: _Optional[_Union[ServiceEvent, _Mapping]] = ...,
        load_evt: _Optional[_Union[LoadHintEvent, _Mapping]] = ...,
        user_evt: _Optional[bytes] = ...,
    ) -> None: ...
