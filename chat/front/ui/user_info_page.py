import asyncio

from base.page import BasePage, ctrl_map
from base.app import BaseApp
from utils.terminal import readline
from models.message import MessageStore
from models.user import User
from sessions.user import UserSession

user_info = "Detailed Info:\n"
user_info_store = MessageStore(5, user_info)


class UserInfoPage(BasePage):
    def __init__(self, name: str, store: MessageStore):
        super().__init__(name, store)
        self.user: User

    def set_user(self, user: User):
        self.user = user

    def show_user_panel(self, session: UserSession):
        def format_line(field: str, value: str):
            return f"{field:<10}: {value}\n"

        store = self.store
        store.append(format_line("email", self.user.email))
        store.append(format_line("username", self.user.username))
        user_seq = self.user.seq
        if session.user_seq != user_seq:
            friend = session.friends[user_seq]
            store.append(format_line("remark", friend.remark or "###"))

        self.redraw_output()

    async def interaction(self, reader: asyncio.StreamReader):
        app: BaseApp = self.app
        session = app.active_user_session

        self.show_user_panel(session)

        selection = await readline(reader)
        ctrl = ctrl_map.get(selection)
        if ctrl is not None:
            return ctrl
