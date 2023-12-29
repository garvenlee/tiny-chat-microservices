from ..user import user_pb2 as _user_pb2
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

class AuthOpStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    AUTH_SUCCESS: _ClassVar[AuthOpStatus]
    AUTH_FAILED: _ClassVar[AuthOpStatus]
    AUTH_EXPIRED: _ClassVar[AuthOpStatus]
    AUTH_TIMEOUT: _ClassVar[AuthOpStatus]

class AuthFailedDetailedInfo(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    AUTH_INCORRECT_EMAIL: _ClassVar[AuthFailedDetailedInfo]
    AUTH_INCORRECT_PWD: _ClassVar[AuthFailedDetailedInfo]
    AUTH_INCORRECT_CONFIRMATION: _ClassVar[AuthFailedDetailedInfo]
    AUTH_NOT_EXISTS: _ClassVar[AuthFailedDetailedInfo]
    AUTH_ALREADY_EXISTS: _ClassVar[AuthFailedDetailedInfo]
    AUTH_UNKNOWN_ERROR: _ClassVar[AuthFailedDetailedInfo]

AUTH_SUCCESS: AuthOpStatus
AUTH_FAILED: AuthOpStatus
AUTH_EXPIRED: AuthOpStatus
AUTH_TIMEOUT: AuthOpStatus
AUTH_INCORRECT_EMAIL: AuthFailedDetailedInfo
AUTH_INCORRECT_PWD: AuthFailedDetailedInfo
AUTH_INCORRECT_CONFIRMATION: AuthFailedDetailedInfo
AUTH_NOT_EXISTS: AuthFailedDetailedInfo
AUTH_ALREADY_EXISTS: AuthFailedDetailedInfo
AUTH_UNKNOWN_ERROR: AuthFailedDetailedInfo

class AuthLoginRequest(_message.Message):
    __slots__ = ["email", "password"]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    PASSWORD_FIELD_NUMBER: _ClassVar[int]
    email: str
    password: str
    def __init__(
        self, email: _Optional[str] = ..., password: _Optional[str] = ...
    ) -> None: ...

class AuthLoginReply(_message.Message):
    __slots__ = ["status", "info", "user", "access_token", "refresh_token"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    INFO_FIELD_NUMBER: _ClassVar[int]
    USER_FIELD_NUMBER: _ClassVar[int]
    ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    REFRESH_TOKEN_FIELD_NUMBER: _ClassVar[int]
    status: AuthOpStatus
    info: AuthFailedDetailedInfo
    user: _user_pb2.UserDetailedInfo
    access_token: str
    refresh_token: str
    def __init__(
        self,
        status: _Optional[_Union[AuthOpStatus, str]] = ...,
        info: _Optional[_Union[AuthFailedDetailedInfo, str]] = ...,
        user: _Optional[_Union[_user_pb2.UserDetailedInfo, _Mapping]] = ...,
        access_token: _Optional[str] = ...,
        refresh_token: _Optional[str] = ...,
    ) -> None: ...

class AuthLogoutRequest(_message.Message):
    __slots__ = ["uid"]
    UID_FIELD_NUMBER: _ClassVar[int]
    uid: int
    def __init__(self, uid: _Optional[int] = ...) -> None: ...

class AuthLogoutReply(_message.Message):
    __slots__ = ["status"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: AuthOpStatus
    def __init__(self, status: _Optional[_Union[AuthOpStatus, str]] = ...) -> None: ...

class AuthRegisterRequest(_message.Message):
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

class AuthRegisterReply(_message.Message):
    __slots__ = ["status", "info", "token"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    INFO_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    status: AuthOpStatus
    info: AuthFailedDetailedInfo
    token: str
    def __init__(
        self,
        status: _Optional[_Union[AuthOpStatus, str]] = ...,
        info: _Optional[_Union[AuthFailedDetailedInfo, str]] = ...,
        token: _Optional[str] = ...,
    ) -> None: ...

class AuthRegisterConfirmRequest(_message.Message):
    __slots__ = ["token"]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    token: str
    def __init__(self, token: _Optional[str] = ...) -> None: ...

class AuthRegisterConfirmReply(_message.Message):
    __slots__ = ["status", "info", "email"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    INFO_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    status: AuthOpStatus
    info: AuthFailedDetailedInfo
    email: str
    def __init__(
        self,
        status: _Optional[_Union[AuthOpStatus, str]] = ...,
        info: _Optional[_Union[AuthFailedDetailedInfo, str]] = ...,
        email: _Optional[str] = ...,
    ) -> None: ...

class AuthTokenRequest(_message.Message):
    __slots__ = ["access_token"]
    ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    access_token: str
    def __init__(self, access_token: _Optional[str] = ...) -> None: ...

class AuthTokenReply(_message.Message):
    __slots__ = ["status", "uid"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    UID_FIELD_NUMBER: _ClassVar[int]
    status: AuthOpStatus
    uid: int
    def __init__(
        self,
        status: _Optional[_Union[AuthOpStatus, str]] = ...,
        uid: _Optional[int] = ...,
    ) -> None: ...

class AuthRefreshTokenRequest(_message.Message):
    __slots__ = ["uid", "refresh_token"]
    UID_FIELD_NUMBER: _ClassVar[int]
    REFRESH_TOKEN_FIELD_NUMBER: _ClassVar[int]
    uid: int
    refresh_token: str
    def __init__(
        self, uid: _Optional[int] = ..., refresh_token: _Optional[str] = ...
    ) -> None: ...

class AuthRefreshTokenReply(_message.Message):
    __slots__ = ["status", "access_token", "refresh_token"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ACCESS_TOKEN_FIELD_NUMBER: _ClassVar[int]
    REFRESH_TOKEN_FIELD_NUMBER: _ClassVar[int]
    status: AuthOpStatus
    access_token: str
    refresh_token: str
    def __init__(
        self,
        status: _Optional[_Union[AuthOpStatus, str]] = ...,
        access_token: _Optional[str] = ...,
        refresh_token: _Optional[str] = ...,
    ) -> None: ...
