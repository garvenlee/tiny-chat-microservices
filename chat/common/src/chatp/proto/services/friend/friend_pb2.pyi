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

class FriendOpStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    FRIEND_SUCCESS: _ClassVar[FriendOpStatus]
    FRIEND_FAILED: _ClassVar[FriendOpStatus]
    FRIEND_TIMEOUT: _ClassVar[FriendOpStatus]

class FriendRequestAction(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    ACCEPTED: _ClassVar[FriendRequestAction]
    REJECTED: _ClassVar[FriendRequestAction]
    IGNORED: _ClassVar[FriendRequestAction]

class FriendEventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
    FRIEND_REQUEST: _ClassVar[FriendEventType]
    FRIEND_CONFIRM: _ClassVar[FriendEventType]
    FRIEND_SESSION: _ClassVar[FriendEventType]

FRIEND_SUCCESS: FriendOpStatus
FRIEND_FAILED: FriendOpStatus
FRIEND_TIMEOUT: FriendOpStatus
ACCEPTED: FriendRequestAction
REJECTED: FriendRequestAction
IGNORED: FriendRequestAction
FRIEND_REQUEST: FriendEventType
FRIEND_CONFIRM: FriendEventType
FRIEND_SESSION: FriendEventType

class FriendDetailedInfo(_message.Message):
    __slots__ = ["session_id", "seq", "uid", "username", "email", "remark"]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    UID_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    REMARK_FIELD_NUMBER: _ClassVar[int]
    session_id: int
    seq: int
    uid: bytes
    username: str
    email: str
    remark: str
    def __init__(
        self,
        session_id: _Optional[int] = ...,
        seq: _Optional[int] = ...,
        uid: _Optional[bytes] = ...,
        username: _Optional[str] = ...,
        email: _Optional[str] = ...,
        remark: _Optional[str] = ...,
    ) -> None: ...

class FriendListRequest(_message.Message):
    __slots__ = ["seq"]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    seq: int
    def __init__(self, seq: _Optional[int] = ...) -> None: ...

class FriendListReply(_message.Message):
    __slots__ = ["status", "friends"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    FRIENDS_FIELD_NUMBER: _ClassVar[int]
    status: FriendOpStatus
    friends: _containers.RepeatedCompositeFieldContainer[FriendDetailedInfo]
    def __init__(
        self,
        status: _Optional[_Union[FriendOpStatus, str]] = ...,
        friends: _Optional[_Iterable[_Union[FriendDetailedInfo, _Mapping]]] = ...,
    ) -> None: ...

class RelationLink(_message.Message):
    __slots__ = ["request_id", "address_id"]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ADDRESS_ID_FIELD_NUMBER: _ClassVar[int]
    request_id: int
    address_id: int
    def __init__(
        self, request_id: _Optional[int] = ..., address_id: _Optional[int] = ...
    ) -> None: ...

class FriendRequest(_message.Message):
    __slots__ = ["uid", "email", "username", "link", "request_msg"]
    UID_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    LINK_FIELD_NUMBER: _ClassVar[int]
    REQUEST_MSG_FIELD_NUMBER: _ClassVar[int]
    uid: bytes
    email: str
    username: str
    link: RelationLink
    request_msg: str
    def __init__(
        self,
        uid: _Optional[bytes] = ...,
        email: _Optional[str] = ...,
        username: _Optional[str] = ...,
        link: _Optional[_Union[RelationLink, _Mapping]] = ...,
        request_msg: _Optional[str] = ...,
    ) -> None: ...

class FriendRequestBatch(_message.Message):
    __slots__ = ["requests"]
    REQUESTS_FIELD_NUMBER: _ClassVar[int]
    requests: _containers.RepeatedCompositeFieldContainer[FriendRequest]
    def __init__(
        self, requests: _Optional[_Iterable[_Union[FriendRequest, _Mapping]]] = ...
    ) -> None: ...

class FriendConfirm(_message.Message):
    __slots__ = ["link", "action", "session_id"]
    LINK_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    link: RelationLink
    action: FriendRequestAction
    session_id: int
    def __init__(
        self,
        link: _Optional[_Union[RelationLink, _Mapping]] = ...,
        action: _Optional[_Union[FriendRequestAction, str]] = ...,
        session_id: _Optional[int] = ...,
    ) -> None: ...

class FriendSession(_message.Message):
    __slots__ = ["link", "session_id"]
    LINK_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    link: RelationLink
    session_id: int
    def __init__(
        self,
        link: _Optional[_Union[RelationLink, _Mapping]] = ...,
        session_id: _Optional[int] = ...,
    ) -> None: ...

class FriendEvent(_message.Message):
    __slots__ = ["evt_tp", "request", "confirm", "session"]
    EVT_TP_FIELD_NUMBER: _ClassVar[int]
    REQUEST_FIELD_NUMBER: _ClassVar[int]
    CONFIRM_FIELD_NUMBER: _ClassVar[int]
    SESSION_FIELD_NUMBER: _ClassVar[int]
    evt_tp: FriendEventType
    request: FriendRequest
    confirm: FriendConfirm
    session: FriendSession
    def __init__(
        self,
        evt_tp: _Optional[_Union[FriendEventType, str]] = ...,
        request: _Optional[_Union[FriendRequest, _Mapping]] = ...,
        confirm: _Optional[_Union[FriendConfirm, _Mapping]] = ...,
        session: _Optional[_Union[FriendSession, _Mapping]] = ...,
    ) -> None: ...

class FriendRequestReply(_message.Message):
    __slots__ = ["status"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: FriendOpStatus
    def __init__(
        self, status: _Optional[_Union[FriendOpStatus, str]] = ...
    ) -> None: ...

class FriendConfirmReply(_message.Message):
    __slots__ = ["status"]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: FriendOpStatus
    def __init__(
        self, status: _Optional[_Union[FriendOpStatus, str]] = ...
    ) -> None: ...

class FriendRequestAck(_message.Message):
    __slots__ = ["link"]
    LINK_FIELD_NUMBER: _ClassVar[int]
    link: RelationLink
    def __init__(
        self, link: _Optional[_Union[RelationLink, _Mapping]] = ...
    ) -> None: ...

class FriendConfirmAck(_message.Message):
    __slots__ = ["link"]
    LINK_FIELD_NUMBER: _ClassVar[int]
    link: RelationLink
    def __init__(
        self, link: _Optional[_Union[RelationLink, _Mapping]] = ...
    ) -> None: ...

class FriendSessionAck(_message.Message):
    __slots__ = ["link"]
    LINK_FIELD_NUMBER: _ClassVar[int]
    link: RelationLink
    def __init__(
        self, link: _Optional[_Union[RelationLink, _Mapping]] = ...
    ) -> None: ...
