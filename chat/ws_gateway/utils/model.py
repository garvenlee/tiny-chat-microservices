from enum import IntEnum
from dataclasses import dataclass


class SessionState(IntEnum):
    IDLE = 0
    ACTIVE = 1
    CLOSING = 2
    CLOSED = 3


SESSION_IDLE = SessionState.IDLE
SESSION_ACTIVE = SessionState.ACTIVE
SESSION_CLOSING = SessionState.CLOSING
SESSION_CLOSED = SessionState.CLOSED


WS_1000_NORMAL_CLOSURE = 1000
WS_1001_GOING_AWAY = 1001
WS_1002_PROTOCOL_ERROR = 1002
WS_1003_UNSUPPORTED_DATA = 1003
WS_1005_NO_STATUS_RCVD = 1005
WS_1006_ABNORMAL_CLOSURE = 1006
WS_1007_INVALID_FRAME_PAYLOAD_DATA = 1007
WS_1008_POLICY_VIOLATION = 1008
WS_1009_MESSAGE_TOO_BIG = 1009
WS_1010_MANDATORY_EXT = 1010
WS_1011_INTERNAL_ERROR = 1011
WS_1012_SERVICE_RESTART = 1012
WS_1013_TRY_AGAIN_LATER = 1013
WS_1014_BAD_GATEWAY = 1014
WS_1015_TLS_HANDSHAKE = 1015

WS_4001_REFRESH_REQUIRED = 4001
WS_4003_NEGOTIATE_TIMEOUT = 4003
WS_4004_SERVER_SHUTDOWN = 4004
WS_4005_SEND_TOO_FAST = 4005
WS_4007_KICKED_OFF = 4007
WS_4008_CONNECT_CONFLICT = 4008


@dataclass
class CacheLine:
    message_id: int
