from typing import Union
from itertools import repeat
from asyncio import StreamReader

from models.message import MessageStore
from utils.terminal import (
    write,
    flush,
    protect_current_position,
    clear_certain_line,
    move_to_certain_line,
    FontStyle,
    FontColors,
    ENDC,
)


class Quit:
    pass


class Back:
    pass


quit_tag = "quit\n"
back_tag = "back\n"

ctrl_map = {quit_tag: Quit, back_tag: Back}


class BasePage:
    __slots__ = "name", "store", "app", "show_notification_in_duration"

    def __init__(self, name: str, store: MessageStore):
        self.name = name
        self.store = store

    def bind(self, app):  # circular reference
        self.app = app

    def write_iter(self, iterable):
        for item in iterable:
            write(item)
        flush()

    def render(self):
        self.store.reset()
        self.redraw_output()

    @protect_current_position
    def redraw_output(self):
        store = self.store
        move_to_certain_line(store.pending_lineno, store.pending_colnum)

        iterable = store.pending_print()
        self.write_iter(iterable)

    @protect_current_position
    def update_one_section(
        self,
        new_line: str,
        *,
        lineno: int,
        column: int,
        font_style: FontStyle,
        font_color: FontColors,
    ):
        move_to_certain_line(lineno, column)
        write(f"{font_style}{font_color}{new_line}{ENDC}")
        flush()

    @protect_current_position
    def delete_one_section(self, lineno: int, column: int, length: int):
        move_to_certain_line(lineno, column)
        write(" " * length)
        flush()

    @protect_current_position
    def reset(self, line_offset: int):
        store = self.store
        lineno_cursor = store.pending_lineno - 1
        for _ in repeat(None, line_offset):
            text_offset = store.pop()
            for lineno in range(lineno_cursor, lineno_cursor - text_offset, -1):
                clear_certain_line(lineno)

            lineno_cursor -= text_offset
        store.reset()

    async def interaction(
        self,
        reader: StreamReader,
    ) -> Union["BasePage", Quit, None]:
        raise NotImplementedError
