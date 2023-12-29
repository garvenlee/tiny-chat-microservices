from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class LoadItem(_message.Message):
    __slots__ = ["srv_addr", "usage_count"]
    SRV_ADDR_FIELD_NUMBER: _ClassVar[int]
    USAGE_COUNT_FIELD_NUMBER: _ClassVar[int]
    srv_addr: str
    usage_count: int
    def __init__(self, srv_addr: _Optional[str] = ..., usage_count: _Optional[int] = ...) -> None: ...

class LoadInfo(_message.Message):
    __slots__ = ["proc_seq", "srv_name", "total_count", "loads"]
    PROC_SEQ_FIELD_NUMBER: _ClassVar[int]
    SRV_NAME_FIELD_NUMBER: _ClassVar[int]
    TOTAL_COUNT_FIELD_NUMBER: _ClassVar[int]
    LOADS_FIELD_NUMBER: _ClassVar[int]
    proc_seq: int
    srv_name: str
    total_count: int
    loads: _containers.RepeatedCompositeFieldContainer[LoadItem]
    def __init__(self, proc_seq: _Optional[int] = ..., srv_name: _Optional[str] = ..., total_count: _Optional[int] = ..., loads: _Optional[_Iterable[_Union[LoadItem, _Mapping]]] = ...) -> None: ...
