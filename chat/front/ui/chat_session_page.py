from asyncio import StreamReader

from base.app import BaseApp
from base.page import BasePage, ctrl_map
from utils.terminal import readline, ENDC, FontColors, FontStyle
from models.message import MessageStore
from models.chat import PendingLogType
from sessions.user import UserSession
from sessions.chat import ChatSession


chat_session = "Friend: "
chat_session_store = MessageStore(None, chat_session)


# TODO add screen adaptability
def format_new_message(username: str, text: str, *, overflow: int):
    return (
        f"{username}: {text}"
        if len(text) <= overflow
        else f"{username}: {text[:overflow - 3]}..."
    )


def format_timeout_line(line: str):
    return f"{FontStyle.BOLD}{FontColors.ERROR}!{ENDC}\t{line}"


class ChatSessionPage(BasePage):
    def __init__(self, name: str, store: MessageStore):
        super().__init__(name, store)
        self.session: ChatSession

    # TODO support multiline message, make ChatSession.messages_line a widget dict
    def show_message_history(self, session: ChatSession):
        store_append = self.store.append
        timeout_ids = session.timeout_ids
        myself = session.user_session.username
        peer = session.friend_header
        if not timeout_ids:
            for msg in session.messages_timeline.values():  # local seq -> increase
                if msg.is_outbound:
                    store_append(
                        f"{format_new_message(myself, msg.text, overflow=35):>80}\n"
                    )
                else:
                    store_append(f"{format_new_message(peer, msg.text, overflow=35)}\n")
        else:
            curr_timeout_p = 0
            timeout_ids_len = len(timeout_ids)
            curr_timeout_id = timeout_ids[curr_timeout_p]
            for msg in session.messages_timeline.values():
                if msg.is_outbound:
                    if msg.local_id != curr_timeout_id:
                        store_append(f"{msg.text:>80}\n")
                    else:
                        curr_timeout_p += 1
                        if curr_timeout_p < timeout_ids_len:
                            curr_timeout_id = timeout_ids[curr_timeout_p]

                        format_text = format_new_message(myself, msg.text, overflow=35)
                        store_append(f"{format_timeout_line(format_text):>80}\n")
                else:
                    store_append(f"{format_new_message(peer, msg.text, overflow=35)}\n")

        self.redraw_output()

    def set_session(self, session: ChatSession):
        self.session = session

        store_append = self.store.append
        store_append(f"{session.friend.username}\n\n")
        self.show_message_history(session)

        # page updation
        pending_logs = session.pending_logs
        if pending_logs:
            timeout_ids = session.timeout_ids
            for log in pending_logs:
                match log.log_type:
                    case PendingLogType.SENT_ACKED:
                        if timeout_ids:
                            self.on_message_sent_success(log.local_id)
                    case PendingLogType.SENT_TIMEOUT:
                        self.on_message_sent_timeout(log.local_id)
                    case _:
                        pass
            pending_logs.clear()

    def bubble_message(self, local_id: int):
        session = self.session
        hint = format_new_message(
            session.friend_header, session.messages_timeline[local_id].text, overflow=35
        )
        self.store.append(f"{hint}\n")
        self.redraw_output()

    def _locate_timeout_column(self, plain_text: str):
        return 80 - 4 - len(plain_text) - 1

    def on_message_sent_timeout(self, local_id: int):
        messages_timeline = self.session.messages_timeline
        message = messages_timeline[local_id]

        plain_text = message.text
        new_line = format_timeout_line(plain_text)

        lineno = message.local_seq
        self.store.set_line(lineno + 1, new_line)  # store
        self.update_one_section(
            "!",  # timeout tag
            lineno=lineno + 2,
            column=self._locate_timeout_column(plain_text),
            font_style=FontStyle.BOLD,
            font_color=FontColors.ERROR,
        )  # page

    def on_message_sent_success(self, local_id: int):
        session = self.session
        timeout_ids = session.timeout_ids
        for seq, lid in enumerate(timeout_ids):
            if lid == local_id:
                message = session.messages_timeline[local_id]
                plain_text = message.text

                lineno = message.local_seq
                self.store.set_line(lineno + 1, f"{plain_text:>80}\n")
                self.delete_one_section(
                    lineno=lineno + 2,
                    column=self._locate_timeout_column(plain_text),
                    length=1,
                )
                break
        else:
            return

        timeout_ids.pop(seq)

    async def interaction(self, reader: StreamReader):
        store_append = self.store.append

        app: BaseApp = self.app
        user_session: UserSession = app.active_user_session
        user = user_session.user
        user_header = user.username

        chat_session = self.session
        while True:
            message = await readline(reader)
            ctrl = ctrl_map.get(message)
            if ctrl is not None:
                self.store.restore()
                # self.safely_exit()
                return ctrl

            if message.startswith(":!"):  # :!resend#number / :!delete#number
                try:
                    match message[2:9]:
                        case "resend#":
                            seq = int(message[9:])  # start from 1
                            if chat_session.resend_message(seq):
                                continue
                        case "delete#":
                            seq = int(message[9:])
                        case _:
                            pass
                except ValueError:
                    pass

            store_append(f"{user_header:>50}: {message}")
            self.redraw_output()
            chat_session.send_message(message[:-1])
