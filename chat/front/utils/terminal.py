from os import system
from sys import stdout, stdin
from shutil import get_terminal_size
from tty import setcbreak
from termios import tcgetattr, tcsetattr, TCSANOW
from functools import wraps
from collections import deque
from contextlib import asynccontextmanager
from asyncio import StreamReader, StreamReaderProtocol, get_event_loop


write = stdout.write
flush = stdout.flush

_, total_rows = get_terminal_size()
max_rows = total_rows - 1


@asynccontextmanager
async def create_stdin_reader():
    old_info = tcgetattr(stdin.fileno())
    setcbreak(stdin)
    system("clear")

    # create stdin reader
    reader = StreamReader()
    protocol = StreamReaderProtocol(reader)
    loop = get_event_loop()
    await loop.connect_read_pipe(lambda: protocol, stdin)

    try:
        yield reader
    finally:
        # reset stdin
        # dont call transport.close() -> sock.close()
        protocol.connection_lost(None)
        tcsetattr(stdin.fileno(), TCSANOW, old_info)


def async_readline():
    write = stdout.write
    flush = stdout.flush

    def erase_last_char():
        move_back_one_char()
        write(" ")
        move_back_one_char()

    async def inner(reader: StreamReader):
        delete_char = b"\x7f"
        input_buffer = deque()
        while (input_char := await reader.read(1)) != b"\n":
            if input_char == delete_char and len(input_buffer) > 0:
                input_buffer.pop()
                erase_last_char()
                flush()
            else:
                input_buffer.append(input_char)
                write(input_char.decode())
                flush()
        clear_line()
        input_buffer.append(b"\n")
        return b"".join(input_buffer).decode()

    return inner


readline = async_readline()


def save_cursor_postion():
    write("\0337")


def restore_cursor_position():
    write("\0338")


def move_to_top_of_screen():
    write("\033[H")


def move_to_certain_line(lineno: int, colnum: int):
    write(f"\033[{lineno};{colnum}H")


def delete_line():
    write("\033[2K")


def clear_line():
    write("\033[2K\033[0G")


def clear():
    write("\033c")


def clear_certain_line(lineno: int):
    move_to_certain_line(lineno, 1)
    clear_line()


def move_back_one_char():
    write("\033[1D")


def move_to_bottom_of_screen() -> int:
    write(f"\033[{max_rows}E")


def switch_to_new_page():
    clear()
    move_to_bottom_of_screen()


def clear_before_exit():
    clear()
    move_to_top_of_screen()


class FontColors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    ERROR = "\033[91m"


class FontStyle:
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"


ENDC = "\033[0m"


def protect_current_position(func):
    @wraps(func)
    def _inner_impl(*args, **kwargs):
        save_cursor_postion()
        func(*args, **kwargs)
        restore_cursor_position()

    return _inner_impl
