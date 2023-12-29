from asyncio import StreamReader, sleep

from base.page import BasePage, Quit, ctrl_map
from base.app import BaseApp
from base.status_bar import NotificationType

from network.http import SUCCESS
from sessions.user import UserSession
from models.friend import (
    RelationState,
    PENDING_INBOUND,
    PENDING_OUTBOUND,
    ACCEPT_INBOUND,
    REJECT_INBOUND,
    IGNORE_INBOUND,
)
from models.message import MessageStore
from utils.terminal import readline, FontColors, ENDC


hint = (
    "----------------------------------------------------\n"
    "Here are all your friends actions:\n"
)
friend_action_history_store = MessageStore(1000, initial=hint)  # max 1000 friends


class FriendActionHistoryPage(BasePage):
    def __init__(self, name: str, store: MessageStore):
        super().__init__(name, store)

    def show_timeline(self, session: UserSession):
        store = self.store
        for seq, data in enumerate(
            reversed(session.pending_friend_requests.values()), 1
        ):
            user = data.user
            header = f"{seq}.{user.username}"
            if (relation_state := data.state) is PENDING_INBOUND:
                store.append(
                    f"{header:<30}{FontColors.HEADER}A.Accept    B.Reject{ENDC}\n"
                )
            elif relation_state in ACCEPT_INBOUND:
                store.append(f"{header:<30}{FontColors.HEADER}Accepted{ENDC}\n")
            elif relation_state in (PENDING_OUTBOUND, REJECT_INBOUND, IGNORE_INBOUND):
                store.append(f"{header:<30}{FontColors.HEADER}Pending{ENDC}\n")
            else:
                pass

        self.redraw_output()

    async def interaction(self, reader: StreamReader) -> BasePage | Quit | None:
        app: BaseApp = self.app
        session = app.active_user_session
        self.show_timeline(session)

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
                    data = session.timeline[seq - 1]
                    if data.state is not PENDING_INBOUND:
                        raise ValueError("Invalid Option")
                    match option:
                        case "A":
                            action = ACCEPT_INBOUND
                            meth = session.confirm_friend
                        case "B":
                            action = REJECT_INBOUND
                            meth = session.reject_friend
                        case _:
                            raise ValueError("Invalid Option")
                except ValueError:
                    show_notification_in_duration(
                        "Interface Error: unsupported selection.",
                        NotificationType.WARNING,
                    )
                    await sleep(2)
                else:
                    session_id, status = await meth(session.timeline[seq - 1].user.seq)
                    if status is SUCCESS:
                        session.write_local_friend_confirm(
                            seq, action, session_id=session_id
                        )
                        show_notification_in_duration("Already sent FriendConfirm.")
                    else:
                        show_notification_in_duration(
                            f"Found exc in FriendConfirm: {status.name}.",
                            NotificationType.ERROR,
                        )
                        await sleep(2)
