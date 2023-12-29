from typing import Callable, Coroutine
from types import CoroutineType

from asyncio import Task

from models.websocket import WsAppEvent
from sessions.user import UserSession
from sessions.chat import ChatSession

from .status_bar import StatusBar
from .page import BasePage


class BaseApp:
    status_bar: StatusBar
    routes: dict[str, BasePage]
    active_user_session: UserSession
    create_user_session: Callable[[], UserSession]
    create_chat_session: Callable[[int], ChatSession]
    activate_user_session: Callable[[UserSession], None]
    activate_chat_session: Callable[[ChatSession], None]

    create_task: Callable[[CoroutineType], Task]
    create_timer: Callable[[int | float, Coroutine], None]

    def notify(self, event: WsAppEvent, **extra_info):
        pass
