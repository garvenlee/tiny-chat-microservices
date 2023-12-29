from attrs import define
from enum import StrEnum
from typing import NamedTuple, Optional

from google.protobuf.message import Message

from .user import User


@define(slots=True)
class Friend:
    user: User
    # ver1: session_id is uuid4.hex string
    # ver2: session_id is snowflake id
    session_id: Optional[int] = None
    remark: Optional[str] = None

    @property
    def username(self):
        return self.user.username

    @property
    def seq(self):
        return self.user.seq


class RelationState(StrEnum):
    PENDING_INBOUND = "pending_inbound"
    PENDING_OUTBOUND = "pending_outbound"

    ACCEPT_INBOUND = "accept_inbound"
    REJECT_INBOUND = "reject_inbound"
    IGNORE_INBOUND = "ignore_inbound"
    REVOKE_OUTBOUND = "revoke_outbound"


PENDING_INBOUND = RelationState.PENDING_INBOUND
PENDING_OUTBOUND = RelationState.PENDING_OUTBOUND
ACCEPT_INBOUND = RelationState.ACCEPT_INBOUND
REJECT_INBOUND = RelationState.REJECT_INBOUND
IGNORE_INBOUND = RelationState.IGNORE_INBOUND
REVOKE_OUTBOUND = RelationState.REVOKE_OUTBOUND


@define(slots=True)
class FriendRequestData:
    user: User
    state: RelationState
    request_messages: list[str] = []


class FriendConfirmData(NamedTuple):
    confirm: Message
