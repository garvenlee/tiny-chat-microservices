from enum import IntEnum


class MessageType(IntEnum):
    ONLINE_MESSAGE = 0
    FRIEND_REQUEST = 1
    FRIEND_CONFIRM = 2
    USER_KICKED_OFF = 3


class ChannelState(IntEnum):
    ACTIVE = 0
    DIED = 1


class PushException(Exception):
    pass


FAILED_EXCEPTION = PushException("Failed")
TIMEOUT_EXCEPTION = PushException("Timeout")

ACTIVE = ChannelState.ACTIVE
DIED = ChannelState.DIED
