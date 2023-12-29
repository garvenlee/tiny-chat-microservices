from logging import getLogger
from typing import Optional
from functools import partial
from asyncio import BaseEventLoop, sleep, get_running_loop

from network.http import HttpConnection
from network.ws import WsConnection

from .user import UserSession
from .chat import ChatSession

logger = getLogger("session-manager")


class SessionManager:
    HTTP = HttpConnection
    WebSocket = WsConnection

    def __init__(
        self,
        http_host: str,
        http_port: int,
        ws_host: str,
        ws_port: int,
        loop: BaseEventLoop = None,
    ):
        self._loop = loop or get_running_loop()

        # reuse the same connection
        http_conn = self.__class__.HTTP(http_host, http_port)
        ws_conn = self.__class__.WebSocket(ws_host, ws_port)

        self._user_session_factory = partial(
            UserSession, http=http_conn, ws=ws_conn, loop=loop
        )
        self._active_user_session: Optional[UserSession] = None
        self._user_sessions: dict[str, UserSession] = {}

        self._active_chat_session: Optional[ChatSession] = None
        self._chat_sessions: dict[str, ChatSession] = {}

        self._http = http_conn
        self._ws = ws_conn

    def create_user_session(self):
        return self._user_session_factory()

    def activate_user_session(self, session: UserSession):
        self._active_user_session = session
        self._user_sessions[session.user_id] = session

    def create_chat_session(self, session_id: str):
        session = ChatSession(session_id)
        self._chat_sessions[session_id] = session
        return session

    def activate_chat_session(self, session: ChatSession):
        self._active_user_session = session

    async def state_check(self):
        while True:
            await sleep(5)
