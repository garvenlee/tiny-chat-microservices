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

class UserErrorCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    USER_INCORRECT_EMAIL: _ClassVar[UserErrorCode]
    USER_INCORRECT_PWD: _ClassVar[UserErrorCode]
    USER_NOT_EXISTS: _ClassVar[UserErrorCode]
    USER_ALREADY_EXISTS: _ClassVar[UserErrorCode]
    USER_DB_TIMEOUT: _ClassVar[UserErrorCode]
    USER_REDIS_TIMEOUT: _ClassVar[UserErrorCode]
    USER_UNKNOWN_ERROR: _ClassVar[UserErrorCode]

class UserDeviceType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    TERMINAL: _ClassVar[UserDeviceType]
    WEB: _ClassVar[UserDeviceType]
    PC: _ClassVar[UserDeviceType]
    ANDROID: _ClassVar[UserDeviceType]
    IOS: _ClassVar[UserDeviceType]

USER_INCORRECT_EMAIL: UserErrorCode
USER_INCORRECT_PWD: UserErrorCode
USER_NOT_EXISTS: UserErrorCode
USER_ALREADY_EXISTS: UserErrorCode
USER_DB_TIMEOUT: UserErrorCode
USER_REDIS_TIMEOUT: UserErrorCode
USER_UNKNOWN_ERROR: UserErrorCode
TERMINAL: UserDeviceType
WEB: UserDeviceType
PC: UserDeviceType
ANDROID: UserDeviceType
IOS: UserDeviceType

class UserDetailedInfo(_message.Message):
    __slots__ = ["seq", "uid", "username", "email"]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    UID_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    seq: int
    uid: bytes
    username: str
    email: str
    def __init__(
        self,
        seq: _Optional[int] = ...,
        uid: _Optional[bytes] = ...,
        username: _Optional[str] = ...,
        email: _Optional[str] = ...,
    ) -> None: ...

class UserLoginRequest(_message.Message):
    __slots__ = ["email", "password"]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    email: str
    password: str
    def __init__(
        self, email: _Optional[str] = ..., password: _Optional[str] = ...
    ) -> None: ...

class UserLoginReply(_message.Message):
    __slots__ = ["success", "code", "user"]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    USER_FIELD_NUMBER: _ClassVar[int]
    success: bool
    code: UserErrorCode
    user: UserDetailedInfo
    def __init__(
        self,
        success: bool = ...,
        code: _Optional[_Union[UserErrorCode, str]] = ...,
        user: _Optional[_Union[UserDetailedInfo, _Mapping]] = ...,
    ) -> None: ...

class UserRegisterRequest(_message.Message):
    __slots__ = ["username", "email", "password"]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    username: str
    email: str
    password: str
    def __init__(
        self,
        username: _Optional[str] = ...,
        email: _Optional[str] = ...,
        password: _Optional[str] = ...,
    ) -> None: ...

class UserRegisterReply(_message.Message):
    __slots__ = ["success", "code", "seq"]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    success: bool
    code: UserErrorCode
    seq: int
    def __init__(
        self,
        success: bool = ...,
        code: _Optional[_Union[UserErrorCode, str]] = ...,
        seq: _Optional[int] = ...,
    ) -> None: ...

class UserRegisterConfirmRequest(_message.Message):
    __slots__ = ["seq"]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    seq: int
    def __init__(self, seq: _Optional[int] = ...) -> None: ...

class UserRegisterConfirmReply(_message.Message):
    __slots__ = ["success", "code"]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    code: UserErrorCode
    def __init__(
        self, success: bool = ..., code: _Optional[_Union[UserErrorCode, str]] = ...
    ) -> None: ...

class UserQueryRequest(_message.Message):
    __slots__ = ["email"]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    email: str
    def __init__(self, email: _Optional[str] = ...) -> None: ...

class UserQueryReply(_message.Message):
    __slots__ = ["success", "code", "user"]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    USER_FIELD_NUMBER: _ClassVar[int]
    success: bool
    code: UserErrorCode
    user: UserDetailedInfo
    def __init__(
        self,
        success: bool = ...,
        code: _Optional[_Union[UserErrorCode, str]] = ...,
        user: _Optional[_Union[UserDetailedInfo, _Mapping]] = ...,
    ) -> None: ...

class UserKickedOff(_message.Message):
    __slots__ = ["uid", "device_tp", "timestamp"]
    UID_FIELD_NUMBER: _ClassVar[int]
    DEVICE_TP_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    uid: int
    device_tp: UserDeviceType
    timestamp: int
    def __init__(
        self,
        uid: _Optional[int] = ...,
        device_tp: _Optional[_Union[UserDeviceType, str]] = ...,
        timestamp: _Optional[int] = ...,
    ) -> None: ...

class UserLogoutRequest(_message.Message):
    __slots__ = ["seq", "device_tp"]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    DEVICE_TP_FIELD_NUMBER: _ClassVar[int]
    seq: int
    device_tp: UserDeviceType
    def __init__(
        self,
        seq: _Optional[int] = ...,
        device_tp: _Optional[_Union[UserDeviceType, str]] = ...,
    ) -> None: ...

class UserLogoutReply(_message.Message):
    __slots__ = ["success", "code"]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    code: UserErrorCode
    def __init__(
        self, success: bool = ..., code: _Optional[_Union[UserErrorCode, str]] = ...
    ) -> None: ...

class UserOnlineRequest(_message.Message):
    __slots__ = ["seq", "device_tp", "gateway_addr", "online_timestamp"]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    DEVICE_TP_FIELD_NUMBER: _ClassVar[int]
    GATEWAY_ADDR_FIELD_NUMBER: _ClassVar[int]
    ONLINE_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    seq: int
    device_tp: UserDeviceType
    gateway_addr: str
    online_timestamp: int
    def __init__(
        self,
        seq: _Optional[int] = ...,
        device_tp: _Optional[_Union[UserDeviceType, str]] = ...,
        gateway_addr: _Optional[str] = ...,
        online_timestamp: _Optional[int] = ...,
    ) -> None: ...

class UserOnlineReply(_message.Message):
    __slots__ = ["success", "code"]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    code: UserErrorCode
    def __init__(
        self, success: bool = ..., code: _Optional[_Union[UserErrorCode, str]] = ...
    ) -> None: ...

class UserOfflineRequest(_message.Message):
    __slots__ = ["seq", "device_tp", "offline_timestamp"]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    DEVICE_TP_FIELD_NUMBER: _ClassVar[int]
    OFFLINE_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    seq: int
    device_tp: UserDeviceType
    offline_timestamp: int
    def __init__(
        self,
        seq: _Optional[int] = ...,
        device_tp: _Optional[_Union[UserDeviceType, str]] = ...,
        offline_timestamp: _Optional[int] = ...,
    ) -> None: ...

class UserOfflineReply(_message.Message):
    __slots__ = ["success", "code"]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    code: UserErrorCode
    def __init__(
        self, success: bool = ..., code: _Optional[_Union[UserErrorCode, str]] = ...
    ) -> None: ...

class UserOnlineCheckRequest(_message.Message):
    __slots__ = ["seq"]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    seq: int
    def __init__(self, seq: _Optional[int] = ...) -> None: ...

class UserOnlineStatus(_message.Message):
    __slots__ = ["success", "code", "online"]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    ONLINE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    code: UserErrorCode
    online: bool
    def __init__(
        self,
        success: bool = ...,
        code: _Optional[_Union[UserErrorCode, str]] = ...,
        online: bool = ...,
    ) -> None: ...

class UserMultiTerminalCheckRequest(_message.Message):
    __slots__ = ["seq", "device_tp"]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    DEVICE_TP_FIELD_NUMBER: _ClassVar[int]
    seq: int
    device_tp: UserDeviceType
    def __init__(
        self,
        seq: _Optional[int] = ...,
        device_tp: _Optional[_Union[UserDeviceType, str]] = ...,
    ) -> None: ...

class UserMultiTerminalCheckReply(_message.Message):
    __slots__ = ["success", "code", "exists"]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    EXISTS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    code: UserErrorCode
    exists: bool
    def __init__(
        self,
        success: bool = ...,
        code: _Optional[_Union[UserErrorCode, str]] = ...,
        exists: bool = ...,
    ) -> None: ...

class UserGatewayAddrRequest(_message.Message):
    __slots__ = ["seq", "device_tp"]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    DEVICE_TP_FIELD_NUMBER: _ClassVar[int]
    seq: int
    device_tp: UserDeviceType
    def __init__(
        self,
        seq: _Optional[int] = ...,
        device_tp: _Optional[_Union[UserDeviceType, str]] = ...,
    ) -> None: ...

class UserGatewayAddrReply(_message.Message):
    __slots__ = ["success", "code", "gateway_addr"]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    GATEWAY_ADDR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    code: UserErrorCode
    gateway_addr: str
    def __init__(
        self,
        success: bool = ...,
        code: _Optional[_Union[UserErrorCode, str]] = ...,
        gateway_addr: _Optional[str] = ...,
    ) -> None: ...

class UserGatewayAddrsRequest(_message.Message):
    __slots__ = ["seq"]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    seq: int
    def __init__(self, seq: _Optional[int] = ...) -> None: ...

class UserGatewayAddrsReply(_message.Message):
    __slots__ = ["success", "code", "platform_types", "gateway_addrs"]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    CODE_FIELD_NUMBER: _ClassVar[int]
    PLATFORM_TYPES_FIELD_NUMBER: _ClassVar[int]
    GATEWAY_ADDRS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    code: UserErrorCode
    platform_types: _containers.RepeatedScalarFieldContainer[str]
    gateway_addrs: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        success: bool = ...,
        code: _Optional[_Union[UserErrorCode, str]] = ...,
        platform_types: _Optional[_Iterable[str]] = ...,
        gateway_addrs: _Optional[_Iterable[str]] = ...,
    ) -> None: ...
