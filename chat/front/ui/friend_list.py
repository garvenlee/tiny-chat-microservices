from typing import cast
from asyncio import StreamReader

from utils.terminal import readline, FontColors, ENDC
from models.message import MessageStore
from models.friend import Friend
from sessions.user import UserSession

from base.app import BaseApp
from base.page import BasePage, ctrl_map
from base.status_bar import NotificationType

from .chat_session_page import ChatSessionPage
from .user_info_page import UserInfoPage

friend = (
    "----------------------------------------------------\n"
    "The following is your friends list:\n"
)
friend_list_store = MessageStore(1000, initial=friend)  # max 1000 friends


class FriendListPage(BasePage):
    def __init__(self, name: str, store: MessageStore):
        super().__init__(name, store)

    def show_friends(self, session: UserSession):
        store = self.store
        for seq, friend in enumerate(session.friend_list, 1):
            friend = cast(Friend, friend)
            header = f"{seq}.{friend.user.username}"
            store.append(
                f"{header:<30}{FontColors.HEADER}A.Chat    B.Detailed info{ENDC}\n"
            )
        self.redraw_output()

    async def interaction(self, reader: StreamReader):
        # TODO process friend_request & friend_confirm notify here
        app: BaseApp = self.app
        session = app.active_user_session
        self.show_friends(session)

        page: ChatSessionPage | UserInfoPage
        show_notification_in_duration = app.status_bar.show_notification_in_duration
        while True:
            selection = await readline(reader)
            ctrl = ctrl_map.get(selection)
            if ctrl is not None:
                self.store.restore()
                return ctrl
            else:
                try:
                    seq, option = int(selection[:-2]), selection[-2]
                    if seq > len(session.friend_list):
                        raise ValueError("Invalid sequence number")
                    friend: Friend = session.friend_list[seq - 1]
                    match option:
                        case "A":
                            page = app.routes["chat_session_page"]
                            page = cast(ChatSessionPage, page)
                            chat_session = session.get_or_create_chat_session(
                                session.friend_list[seq - 1]
                            )
                            page.set_session(chat_session)
                        case "B":
                            page = app.routes["user_info_page"]
                            page = cast(UserInfoPage, page)
                            page.set_user(friend.user)
                        case _:
                            raise ValueError("Invalid option")
                except ValueError as exc:
                    show_notification_in_duration(
                        f"Interface Error: {exc.args[0]}",
                        NotificationType.WARNING,
                    )
                else:
                    self.store.restore()
                    return page
