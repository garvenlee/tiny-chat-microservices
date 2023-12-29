from itertools import repeat

from asyncio import StreamReader, sleep

from base.app import BaseApp
from base.page import BasePage, ctrl_map
from base.status_bar import NotificationType

from models.message import MessageStore
from sessions.user import UserSession
from network.http import SUCCESS
from utils.terminal import readline, clear


register = "Please input your user info:\n" "Enter username: "
register_store = MessageStore(10, register)


class RegisterPage(BasePage):
    def __init__(self, name: str, store: MessageStore):
        super().__init__(name, store)

    async def interaction(self, reader: StreamReader):
        store = self.store
        app: BaseApp = self.app
        session: UserSession = app.create_user_session()

        show_notification_in_duration = app.status_bar.show_notification_in_duration
        while True:
            username: str = await readline(reader)
            ctrl = ctrl_map.get(username)
            if ctrl is not None:
                return ctrl

            store.append(username)
            store.append("Enter email: ")
            self.redraw_output()

            email: str = await readline(reader)
            ctrl = ctrl_map.get(email)
            if ctrl is not None:
                store.restore()
                return ctrl

            store.append(email)
            store.append("Enter password: ")
            self.redraw_output()

            password: str = await readline(reader)
            ctrl = ctrl_map.get(password)
            if ctrl is not None:
                store.restore()
                return ctrl

            store.append(password)
            self.redraw_output()

            username = username.strip()
            email = email.strip()
            password = password.strip()
            # TODO add register dup row hint
            status = await session.register(email, password, username)
            if status is SUCCESS:
                show_notification_in_duration("Registered Successfully.", timeout=2)
                store.restore()
                break
            else:
                show_notification_in_duration(
                    f"Failed to Register: {status.name}",
                    NotificationType.WARNING,
                    timeout=2,
                )

            self.reset(5)
            self.redraw_output()
            await sleep(0)
        return app.routes["login_page"]
