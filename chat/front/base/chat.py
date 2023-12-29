class BaseChatHandler:
    @property
    def username(self):
        ...

    def send_message(self, text: str, *, receiver_id: int, session_id: str) -> int:
        raise NotImplementedError

    def resend_message(self, text: str, *, delivery_id: int) -> None:
        raise NotImplementedError
