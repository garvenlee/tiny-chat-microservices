from contextlib import suppress

from models.friend import Friend
from models.chat import TextMessage, PendingLogType, PendingLog
from base.chat import BaseChatHandler


class ChatSession:
    __slots__ = (
        "friend",
        "user_session",
        "pending_logs",
        "timeout_ids",
        "messages_timeline",
    )

    def __init__(self, friend: Friend):
        self.friend = friend
        self.pending_logs: list[PendingLog] = []

        # dict insertion holds the sequence
        self.timeout_ids: list[int] = []
        self.messages_timeline: dict[int, TextMessage] = dict()

    @property
    def session_id(self):
        return self.friend.session_id

    @property
    def friend_header(self):
        return self.friend.username

    @property
    def friend_id(self):
        return self.friend.seq

    def bind(self, user_session: BaseChatHandler):
        self.user_session = user_session

    def resend_message(self, seq: int):
        timeout_ids = self.timeout_ids
        if 1 <= seq <= len(timeout_ids):  # valid
            local_id = self.timeout_ids[seq - 1]
            text = self.messages_timeline[local_id].text
            self.user_session.resend_message(text, delivery_id=local_id)
            return True
        return False

    def send_message(self, text: str) -> None:
        friend = self.friend
        local_id = self.user_session.send_message(
            text, receiver_id=friend.seq, session_id=friend.session_id
        )

        messages_timeline = self.messages_timeline
        local_seq = len(messages_timeline) + 1
        messages_timeline[local_id] = TextMessage(local_seq, local_id, text)

    def recv_message(
        self,
        text: str,
        *,
        local_id: int,
        message_id: int,
        is_outbound: bool = False,
    ) -> None:
        messages_timeline = self.messages_timeline
        self.messages_timeline[local_id] = TextMessage(
            len(messages_timeline) + 1,
            local_id,
            text,
            message_id,
            is_outbound=is_outbound,
        )

    def on_acked_timeout(self, local_id: int):
        self.timeout_ids.append(local_id)

    def on_acked_success(self, local_id: int, message_id: int):
        self.messages_timeline[local_id].message_id = message_id
        with suppress(ValueError):
            self.timeout_ids.remove(local_id)

    def append_log(self, local_id: int, log_type: PendingLogType):
        self.pending_logs.append(PendingLog(log_type=log_type, local_id=local_id))
