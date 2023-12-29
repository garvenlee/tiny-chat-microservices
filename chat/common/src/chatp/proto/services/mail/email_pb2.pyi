from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class email(_message.Message):
    __slots__ = ["link", "template", "to_addr"]
    LINK_FIELD_NUMBER: _ClassVar[int]
    TEMPLATE_FIELD_NUMBER: _ClassVar[int]
    TO_ADDR_FIELD_NUMBER: _ClassVar[int]
    link: str
    template: str
    to_addr: str
    def __init__(self, to_addr: _Optional[str] = ..., template: _Optional[str] = ..., link: _Optional[str] = ...) -> None: ...
