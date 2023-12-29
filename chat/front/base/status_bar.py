from enum import StrEnum
from typing import Optional, NamedTuple

from asyncio import TimerHandle, BaseEventLoop, get_running_loop

from utils.terminal import (
    FontColors,
    FontStyle,
    ENDC,
    write,
    flush,
    protect_current_position,
    clear_certain_line,
    move_to_certain_line,
)


class NotificationType(StrEnum):
    INFO = "INFO"
    WARNING = "warning"
    ERROR = "error"


class Notification(NamedTuple):
    text: str
    tp: NotificationType = NotificationType.INFO


color_map = {
    NotificationType.INFO: FontColors.OKCYAN,
    NotificationType.WARNING: FontColors.WARNING,
    NotificationType.ERROR: FontColors.ERROR,
}

ROUND_LOOP = 86400


class StatusBar:
    """
    app_name | page_name [- username[email]] [NotificationRegion]
    """

    __slots__ = (
        "_loop",
        "app_name",
        "page_name",
        "username",
        "email",
        "notifications",
        "notification_idx",
        "notification_ver",
        "notification_timer",
    )

    def __init__(
        self, app_name: str = "chatApp", *, loop: Optional[BaseEventLoop] = None
    ):
        self.app_name = app_name
        self.page_name: Optional[str] = None
        self.username: Optional[str] = None
        self.email: Optional[str] = None

        self.notifications: list[Notification] = []

        self.notification_idx = -1
        self.notification_ver = 0
        self.notification_timer: Optional[TimerHandle] = None

        if loop is None:
            loop = get_running_loop()
        self._loop = loop

    @property
    def user_info(self):
        username, email = self.username, self.email
        username_len, email_len = len(username), len(email)
        assert username_len <= 15
        if username_len + email_len + 2 <= 30:
            return f"{username}[{email}]"
        else:
            return f"{username}[{email[:30 - username_len - 2 - 3]}...]"

    @property
    def notification_loc(self):
        if self.username is not None:
            return len(self.app_name) + 3 + len(self.page_name) + 3 + 30 + 5
        else:
            return len(self.app_name) + 3 + len(self.page_name) + 5

    def set_page_name(self, page_name: str):
        self.page_name = page_name

    def bind_user(self, username: str, email: str):
        self.username = username
        self.email = email

    def _render_line(self):
        write(f"{FontStyle.BOLD}{FontColors.HEADER}{self.app_name} | {self.page_name}")
        if self.username is not None:
            write(f" - {self.user_info:<30}{ENDC}")
        else:
            write(ENDC)
        flush()

    @protect_current_position
    def clear_and_render(self):
        clear_certain_line(1)
        self._render_line()

    @protect_current_position
    def render(self):
        move_to_certain_line(1, 1)
        self._render_line()

    @protect_current_position
    def clear_notification(self, text_len: int, notification_ver: int):
        if self.notification_ver == notification_ver:
            move_to_certain_line(1, self.notification_loc)

            write(" " * text_len)
            flush()

            self.notification_timer = None

    def show_notification_in_duration(
        self,
        text: str,
        tp: NotificationType = NotificationType.INFO,
        timeout: int | float = 3,
    ):
        if self.notification_timer is not None:
            self.notification_timer.cancel()
            self.clear_and_render()

        self.blink_notification(text, tp)
        self.notification_timer = self._loop.call_later(
            timeout, self.clear_notification, len(text), self.notification_ver
        )

    @protect_current_position
    def blink_notification(
        self, text: str, tp: NotificationType = NotificationType.INFO
    ):
        move_to_certain_line(1, self.notification_loc)

        font_color = color_map[tp]
        write(f"{FontStyle.BLINK}{font_color}{text}{ENDC}")
        flush()

        self.notification_ver += 1
        self.notification_ver %= ROUND_LOOP

    @protect_current_position
    def cycle_notification(self):
        move_to_certain_line(1, self.notification_loc)

        notification = self.notifications[self.notification_idx]
        font_color = color_map[notification.tp]
        write(f"{FontStyle.BLINK}{font_color}{notification}{ENDC}")
        flush()
        self.notification_idx += 1
        self.notification_idx %= len(self.notifications)
