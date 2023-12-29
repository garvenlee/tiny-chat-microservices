from enum import IntEnum
from dataclasses import dataclass
from typing import NamedTuple, Optional, Tuple


@dataclass
class RefreshTokenKey:
    uid: int

    def __str__(self) -> str:
        return f"chatp:auth:refresh_token:uid:{self.uid}"


class AuthStatus(IntEnum):
    Success = 0
    Expired = 1
    InvalidToken = 2
    InvalidSignature = 3
    InvalidPayload = 4


class AuthCredentials(NamedTuple):
    uid: int
    tokens: Optional[Tuple] = None  # access_token, refresh_token
