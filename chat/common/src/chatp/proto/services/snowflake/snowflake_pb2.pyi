from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class BusinessKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    SNOWFLAKE_SESSION: _ClassVar[BusinessKind]
    SNOWFLAKE_MESSAGE: _ClassVar[BusinessKind]
    SNOWFLAKE_USER_DEFINED: _ClassVar[BusinessKind]

SNOWFLAKE_SESSION: BusinessKind
SNOWFLAKE_MESSAGE: BusinessKind
SNOWFLAKE_USER_DEFINED: BusinessKind

class SnowflakeRequest(_message.Message):
    __slots__ = ["kind"]
    KIND_FIELD_NUMBER: _ClassVar[int]
    kind: BusinessKind
    def __init__(self, kind: _Optional[_Union[BusinessKind, str]] = ...) -> None: ...

class SnowflakeReply(_message.Message):
    __slots__ = ["snowflake_id"]
    SNOWFLAKE_ID_FIELD_NUMBER: _ClassVar[int]
    snowflake_id: int
    def __init__(self, snowflake_id: _Optional[int] = ...) -> None: ...
