from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class StatusFrame(_message.Message):
    __slots__ = ["kicked_off", "extra"]
    KICKED_OFF_FIELD_NUMBER: _ClassVar[int]
    EXTRA_FIELD_NUMBER: _ClassVar[int]
    kicked_off: bool
    extra: bytes
    def __init__(
        self, kicked_off: bool = ..., extra: _Optional[bytes] = ...
    ) -> None: ...
