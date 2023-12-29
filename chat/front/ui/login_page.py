from asyncio import StreamReader, sleep

from base.app import BaseApp
from base.page import BasePage, ctrl_map
from base.status_bar import NotificationType

from utils.terminal import readline
from models.websocket import (
    CONNECTED,
    LOGIN_TIMEOUT,
    REJECTED,
    REFRESH_REQUIRED,
    LOGIN_CONFLICT,
    NEGOTIATE_TIMEOUT,
    KICKED_OFF,
    INBOUND_FRIEND_REQUEST,
    INBOUND_FRIEND_CONFIRM,
    INBOUND_MESSAGE,
    INBOUND_ACKED_MESSAGE,
    OUTBOUND_MESSAGE_TIMEOUT,
    NETWORK_ERROR,
)
from sessions.user import UserSession
from models.message import MessageStore
from network.http import SUCCESS

login = "Please input your user info:\n" "Enter email: "
login_store = MessageStore(10, login)


class LoginPage(BasePage):
    def __init__(self, name: str, store: MessageStore):
        super().__init__(name, store)

    async def wait_to_load_info(self, status_code: int):
        pass

    @staticmethod
    def register_callbacks(app: BaseApp):
        show_notification_in_duration = app.status_bar.show_notification_in_duration
        notification_cb = lambda text: show_notification_in_duration(text)

        session = app.active_user_session
        session.register_callback(INBOUND_FRIEND_REQUEST, notification_cb)
        session.register_callback(INBOUND_FRIEND_CONFIRM, notification_cb)

        session.register_callback(
            INBOUND_MESSAGE,
            lambda sender_id, local_id: app.notify(
                INBOUND_MESSAGE,
                sender_id=sender_id,
                local_id=local_id,
            ),  # partial method may be better, but args is blurred
        )
        session.register_callback(
            OUTBOUND_MESSAGE_TIMEOUT,
            lambda receiver_id, local_id: app.notify(
                OUTBOUND_MESSAGE_TIMEOUT,
                receiver_id=receiver_id,
                local_id=local_id,
            ),
        )
        session.register_callback(
            INBOUND_ACKED_MESSAGE,
            lambda receiver_id, local_id: app.notify(
                INBOUND_ACKED_MESSAGE,
                receiver_id=receiver_id,
                local_id=local_id,
            ),
        )

    async def interaction(self, reader: StreamReader):
        store = self.store
        app: BaseApp = self.app
        session: UserSession = app.create_user_session()
        session.register_callback(
            KICKED_OFF, lambda text: app.notify(KICKED_OFF, text=text)
        )
        # session.register_callback(
        #     NETWORK_ERROR, lambda **kwargs: app.notify(NETWORK_ERROR, **kwargs)
        # )

        last_email = ws_connect_task = None
        show_notification_in_duration = app.status_bar.show_notification_in_duration
        while True:
            email: str = await readline(reader)
            ctrl = ctrl_map.get(email)
            if ctrl is not None:
                if ws_connect_task is not None:
                    ws_connect_task.cancel()
                return ctrl

            store.append(email)
            store.append("Enter password: ")
            self.redraw_output()

            password: str = await readline(reader)
            ctrl = ctrl_map.get(password)
            if ctrl is not None:
                store.pop()
                store.pop()
                store.reset()
                if ws_connect_task is not None:
                    ws_connect_task.cancel()
                return ctrl

            store.append(password)
            self.redraw_output()

            email = email.strip()
            password = password.strip()

            show_notification_in_duration(
                "connecting...", NotificationType.INFO, timeout=10
            )
            status = await session.login(email, password)  # 5s default
            if status is SUCCESS:
                app.activate_user_session(session)
                # must make sure the same login user
                if session.can_reconnect and last_email == email:
                    session.ready_to_reconnect()
                else:
                    if ws_connect_task is not None:
                        ws_connect_task.cancel()

                    # 3s opend_timeout, 5s negotiate
                    ws_connect_task = app.create_task(session.ws_connect())

                code = await session.wait_for_ws_connected()  # wait 8s default
                if code is CONNECTED:
                    # notification callback
                    show_notification_in_duration("Login Successfully.")

                    # status bar setting
                    app.status_bar.bind_user(session.username, email)

                    # notification callbacks
                    self.register_callbacks(app)

                    # token keepalive - TODO optimize
                    app.create_timer(8 * 86400, session.refresh())  # 8 days
                    # app.create_timer(8 * 86400, app.state_check())
                    # app.create_task(session.get_chat_list())
                    # app.create_task(session.get_friend_list())

                    # pull_inbox
                    task = app.create_task(session.pull_session_messages())
                    session.hold_task(task)

                    store.restore()
                    await sleep(3)
                    return app.routes["main_page"]
                elif code is LOGIN_TIMEOUT:
                    show_notification_in_duration(
                        f"Found Timeout in WsConnect.",
                        NotificationType.WARNING,
                    )
                elif code is NEGOTIATE_TIMEOUT:
                    show_notification_in_duration(
                        f"Found Timeout in NEGOTIATE.",
                        NotificationType.WARNING,
                    )
                elif code is LOGIN_CONFLICT:
                    show_notification_in_duration(
                        f"Found another device in login.",
                        NotificationType.WARNING,
                    )
                elif code is REJECTED:
                    show_notification_in_duration(
                        f"Auth failed. Needs to relogin.",
                        NotificationType.INFO,
                    )
                elif code is REFRESH_REQUIRED:
                    show_notification_in_duration(
                        f"Needs to refresh.",
                        NotificationType.INFO,
                    )
            else:
                show_notification_in_duration(
                    f"Found exc in UserLogin: {status.name}.",
                    NotificationType.ERROR,
                )

            last_email = email
            self.reset(3)
            self.redraw_output()
            # move_to_bottom_of_screen()  # make sure
