from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DeviceType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    Terminal: _ClassVar[DeviceType]
    PC: _ClassVar[DeviceType]
    Web: _ClassVar[DeviceType]
    Andriod: _ClassVar[DeviceType]
    IOS: _ClassVar[DeviceType]
Terminal: DeviceType
PC: DeviceType
Web: DeviceType
Andriod: DeviceType
IOS: DeviceType

class UserSession(_message.Message):
    __slots__ = ["wsid", "device_type", "last_online_time", "last_offline_time"]
    WSID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_TYPE_FIELD_NUMBER: _ClassVar[int]
    LAST_ONLINE_TIME_FIELD_NUMBER: _ClassVar[int]
    LAST_OFFLINE_TIME_FIELD_NUMBER: _ClassVar[int]
    wsid: str
    device_type: _containers.RepeatedScalarFieldContainer[DeviceType]
    last_online_time: int
    last_offline_time: int
    def __init__(self, wsid: _Optional[str] = ..., device_type: _Optional[_Iterable[_Union[DeviceType, str]]] = ..., last_online_time: _Optional[int] = ..., last_offline_time: _Optional[int] = ...) -> None: ...
