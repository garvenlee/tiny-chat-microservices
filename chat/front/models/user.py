from uuid import UUID
from typing import Optional, NamedTuple


class User(NamedTuple):
    seq: int
    uid: UUID
    username: str
    email: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None

    @classmethod
    def create(cls, seq: int):
        return cls(seq, "Nobody", "Anonymous", "example@.com")
