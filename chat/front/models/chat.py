from enum import StrEnum
from datetime import datetime
from typing import NamedTuple

from attrs import define, field


@define(slots=True)
class TextMessage:
    local_seq: int
    local_id: int
    text: str
    message_id: int = field(default=-1)
    is_outbound: bool = field(default=True)
    timestamp: datetime = field(factory=datetime.now)


class PendingLogType(StrEnum):
    SENT_ACKED = "sent_acked"
    SENT_TIMEOUT = "sent_timeout"


class PendingLog(NamedTuple):
    log_type: PendingLogType
    local_id: int
