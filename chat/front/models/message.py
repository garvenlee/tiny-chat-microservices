from collections import deque
from itertools import repeat
from typing import Deque, Optional


from utils.terminal import max_rows


class MessageStore:
    __slots__ = [
        "_max_size",
        "_deque",
        "_length",
        "_lineno_sk",
        "pending_cursor",
        "pending_lineno",
        "pending_colnum",
    ]

    def __init__(self, max_size: int = max_rows, initial: Optional[str] = None) -> None:
        self._max_size = max_size

        self._length = 0
        self._deque: Deque[str] = deque(maxlen=max_size)
        self._lineno_sk: list[int] = []

        if initial:
            self.append(initial)

        self.reset()

    def append(self, item: str, lineno: Optional[int] = None):
        self._lineno_sk.append(lineno or len(item[:-1].strip().split("\n")))
        self._deque.append(item)
        self._length += 1

    def pop(self) -> int:
        self._length -= 1
        self._deque.pop()
        return self._lineno_sk.pop()

    def clear(self):
        self._deque.clear()
        self._deque = None
        self._length = 0

    def reset(self):
        self.pending_cursor = 0  # pending to write: idx in self._deque
        self.pending_lineno = 2  # the first lineo is occupied by status_bar
        self.pending_colnum = 1

    def set_line(self, lineno: int, string: str):
        d = self._deque
        old_string, d[lineno] = d[lineno], string
        return old_string

    def restore(self):
        self.reset()

        if (length := self._length) > 1:
            if length > 96:  # 2 block
                new_queue = deque(self._deque[0], maxlen=self._max_size)
                self._deque = new_queue
            else:
                deque_pop = self._deque.pop
                for _ in repeat(None, length - 1):
                    deque_pop()

            del self._lineno_sk[1:]
            self._length = 1

    def pending_print(self):
        while self.pending_cursor < self._length:
            item = self._deque[self.pending_cursor]
            yield item

            lines = item.split("\n")
            self.pending_lineno += len(lines) - 1

            if item[-1] == "\n":
                self.pending_colnum = 1
            else:
                self.pending_colnum = len(lines[-1]) + 1

            self.pending_cursor += 1
