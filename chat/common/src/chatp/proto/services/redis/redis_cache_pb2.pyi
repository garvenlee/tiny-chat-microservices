from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RedisOpStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    REDIS_SUCCESS: _ClassVar[RedisOpStatus]
    REDIS_FAILED: _ClassVar[RedisOpStatus]
    REDIS_TIMEOUT: _ClassVar[RedisOpStatus]

class RateType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    IP: _ClassVar[RateType]
    TOKEN: _ClassVar[RateType]

class RateCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    RATE_ALLOWED: _ClassVar[RateCode]
    RATE_REJECTED: _ClassVar[RateCode]
    RATE_BLOCKED: _ClassVar[RateCode]
REDIS_SUCCESS: RedisOpStatus
REDIS_FAILED: RedisOpStatus
REDIS_TIMEOUT: RedisOpStatus
IP: RateType
TOKEN: RateType
RATE_ALLOWED: RateCode
RATE_REJECTED: RateCode
RATE_BLOCKED: RateCode

class UnaryGetCommonRequest(_message.Message):
    __slots__ = ["key"]
    KEY_FIELD_NUMBER: _ClassVar[int]
    key: str
    def __init__(self, key: _Optional[str] = ...) -> None: ...

class UnaryGetCommonResp(_message.Message):
    __slots__ = ["status", "err_msg", "value"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERR_MSG_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    status: RedisOpStatus
    err_msg: str
    value: str
    def __init__(self, status: _Optional[_Union[RedisOpStatus, str]] = ..., err_msg: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

class UnarySetCommonRequest(_message.Message):
    __slots__ = ["key", "value"]
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    key: str
    value: str
    def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

class UnarySetCommonResp(_message.Message):
    __slots__ = ["status", "err_msg"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERR_MSG_FIELD_NUMBER: _ClassVar[int]
    status: RedisOpStatus
    err_msg: str
    def __init__(self, status: _Optional[_Union[RedisOpStatus, str]] = ..., err_msg: _Optional[str] = ...) -> None: ...

class MultiGetCommonRequest(_message.Message):
    __slots__ = ["keys"]
    KEYS_FIELD_NUMBER: _ClassVar[int]
    keys: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, keys: _Optional[_Iterable[str]] = ...) -> None: ...

class MultiGetCommonResp(_message.Message):
    __slots__ = ["status", "err_msg", "values"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERR_MSG_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    status: RedisOpStatus
    err_msg: str
    values: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, status: _Optional[_Union[RedisOpStatus, str]] = ..., err_msg: _Optional[str] = ..., values: _Optional[_Iterable[str]] = ...) -> None: ...

class MultiSetCommonRequest(_message.Message):
    __slots__ = ["keys", "values"]
    KEYS_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    keys: _containers.RepeatedScalarFieldContainer[str]
    values: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, keys: _Optional[_Iterable[str]] = ..., values: _Optional[_Iterable[str]] = ...) -> None: ...

class MultiSetCommonResp(_message.Message):
    __slots__ = ["status", "err_msg"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERR_MSG_FIELD_NUMBER: _ClassVar[int]
    status: RedisOpStatus
    err_msg: str
    def __init__(self, status: _Optional[_Union[RedisOpStatus, str]] = ..., err_msg: _Optional[str] = ...) -> None: ...

class RedisListPushRequest(_message.Message):
    __slots__ = ["key", "values"]
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    key: str
    values: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, key: _Optional[str] = ..., values: _Optional[_Iterable[str]] = ...) -> None: ...

class RedisListPushResp(_message.Message):
    __slots__ = ["status", "err_msg"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERR_MSG_FIELD_NUMBER: _ClassVar[int]
    status: RedisOpStatus
    err_msg: str
    def __init__(self, status: _Optional[_Union[RedisOpStatus, str]] = ..., err_msg: _Optional[str] = ...) -> None: ...

class RedisHGetRequest(_message.Message):
    __slots__ = ["key", "field"]
    KEY_FIELD_NUMBER: _ClassVar[int]
    FIELD_FIELD_NUMBER: _ClassVar[int]
    key: str
    field: str
    def __init__(self, key: _Optional[str] = ..., field: _Optional[str] = ...) -> None: ...

class RedisHGetResp(_message.Message):
    __slots__ = ["status", "err_msg", "value"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERR_MSG_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    status: RedisOpStatus
    err_msg: str
    value: str
    def __init__(self, status: _Optional[_Union[RedisOpStatus, str]] = ..., err_msg: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

class RedisHSetRequest(_message.Message):
    __slots__ = ["key", "field", "value"]
    KEY_FIELD_NUMBER: _ClassVar[int]
    FIELD_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    key: str
    field: str
    value: str
    def __init__(self, key: _Optional[str] = ..., field: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

class RedisHSetResp(_message.Message):
    __slots__ = ["status"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: RedisOpStatus
    def __init__(self, status: _Optional[_Union[RedisOpStatus, str]] = ...) -> None: ...

class RedisHDelRequest(_message.Message):
    __slots__ = ["key", "fields"]
    KEY_FIELD_NUMBER: _ClassVar[int]
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    key: str
    fields: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, key: _Optional[str] = ..., fields: _Optional[_Iterable[str]] = ...) -> None: ...

class RedisHDelResp(_message.Message):
    __slots__ = ["status"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: RedisOpStatus
    def __init__(self, status: _Optional[_Union[RedisOpStatus, str]] = ...) -> None: ...

class RedisHGetAllRequest(_message.Message):
    __slots__ = ["key"]
    KEY_FIELD_NUMBER: _ClassVar[int]
    key: str
    def __init__(self, key: _Optional[str] = ...) -> None: ...

class RedisHGetAllResp(_message.Message):
    __slots__ = ["status", "err_msg", "keys", "values"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERR_MSG_FIELD_NUMBER: _ClassVar[int]
    KEYS_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    status: RedisOpStatus
    err_msg: str
    keys: _containers.RepeatedScalarFieldContainer[str]
    values: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, status: _Optional[_Union[RedisOpStatus, str]] = ..., err_msg: _Optional[str] = ..., keys: _Optional[_Iterable[str]] = ..., values: _Optional[_Iterable[str]] = ...) -> None: ...

class RedisDeleteRequest(_message.Message):
    __slots__ = ["key"]
    KEY_FIELD_NUMBER: _ClassVar[int]
    key: str
    def __init__(self, key: _Optional[str] = ...) -> None: ...

class RedisDeleteResp(_message.Message):
    __slots__ = ["status", "err_msg"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERR_MSG_FIELD_NUMBER: _ClassVar[int]
    status: RedisOpStatus
    err_msg: str
    def __init__(self, status: _Optional[_Union[RedisOpStatus, str]] = ..., err_msg: _Optional[str] = ...) -> None: ...

class RedisRateLimiterRequest(_message.Message):
    __slots__ = ["tp", "keys", "argv"]
    TP_FIELD_NUMBER: _ClassVar[int]
    KEYS_FIELD_NUMBER: _ClassVar[int]
    ARGV_FIELD_NUMBER: _ClassVar[int]
    tp: RateType
    keys: _containers.RepeatedScalarFieldContainer[str]
    argv: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, tp: _Optional[_Union[RateType, str]] = ..., keys: _Optional[_Iterable[str]] = ..., argv: _Optional[_Iterable[str]] = ...) -> None: ...

class RedisRateLimiterResp(_message.Message):
    __slots__ = ["status", "code"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    status: RedisOpStatus
    code: RateCode
    def __init__(self, status: _Optional[_Union[RedisOpStatus, str]] = ..., code: _Optional[_Union[RateCode, str]] = ...) -> None: ...
