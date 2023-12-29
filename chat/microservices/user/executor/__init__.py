from .user import UserExecutor
from .friend import FriendExecutor


class DbExecutor(UserExecutor, FriendExecutor):
    pass
