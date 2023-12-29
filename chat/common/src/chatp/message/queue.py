from typing import Optional
from itertools import repeat
from collections import deque


# used in delivery_id/offset: 0, 1, 2, 3, 4, 5...
class RangeSpan:
    __slots__ = "start", "end", "prev", "next"  # [start, end)

    def __init__(self, start: int, end: Optional[int] = None):
        self.start = start
        self.end = end or start + 1
        self.prev: Optional[RangeSpan] = None
        self.next: Optional[RangeSpan] = None


class AckQueue:
    def __init__(self):
        self._query_left: dict[int, RangeSpan] = dict()
        self._query_right: dict[int, RangeSpan] = dict()

        root = RangeSpan(-1)  # [-1, 0)
        root.prev = root.next = root
        self._span_root = root

        self._cnt = 0
        self._iter_loc = 0

        self._cache_spans: deque[RangeSpan] = deque(maxlen=64)

    def add(self, start: int) -> None:
        if start < 0:  # only support id >= 0
            return

        query_l, query_r = self._query_left, self._query_right
        left_span = query_r.get(start)
        right_span = query_l.get(start + 1)

        if left_span is not None and right_span is not None:
            # adjust linked list - remove right_span
            prev_span, next_span = right_span.prev, right_span.next
            prev_span.next = next_span
            next_span.prev = prev_span

            # adjust query table
            del query_r[start]
            del query_l[start + 1]
            query_r[right_span.end] = left_span

            # cache
            self._cnt -= 1
            left_span.end = right_span.end
            self._cache_spans.append(right_span)
        elif left_span is not None:
            left_span.end += 1
            del query_r[start]
            query_r[start + 1] = left_span
        elif right_span is not None:
            right_span.start -= 1
            del query_l[start + 1]
            query_l[start] = right_span
        else:
            if cache_spans := self._cache_spans:
                span = cache_spans.popleft()
                span.start, span.end = start, start + 1
            else:
                span = RangeSpan(start)

            # span's location in the doubly linked list
            root = self._span_root
            if self._cnt == 0:
                root.next = root.prev = span
                span.next = span.prev = root
            else:
                tail = root.prev
                root.prev = span
                tail.next = span
                span.prev = tail
                span.next = root

            self._cnt += 1
            query_l[start] = query_r[start + 1] = span

    def clear(self):
        if self._cnt == 0:
            return

        cache_spans_append = self._cache_spans.append

        root = self._span_root
        node = root.next
        root.prev = root.next = root
        for _ in repeat(None, self._cnt):
            cache_spans_append(node)
            node = node.next

        self._query_left.clear()
        self._query_right.clear()
        self._cnt = 0

    def iterator(self):
        node = self._span_root.next
        for _ in repeat(None, self._cnt):
            yield node
            node = node.next

    def __len__(self) -> int:
        return self._cnt

    def __contains__(self, seq: int):
        node = self._span_root.next
        for _ in repeat(None, self._cnt):
            if node.start <= seq < node.end:
                return True
            node = node.next
        return False

    @property
    def first_end(self):
        return self._span_root.next.end


if __name__ == "__main__":
    queue = AckQueue()
    queue.add(3)
    queue.add(5)
    queue.add(7)
    queue.add(6)
    queue.add(4)
    queue.add(1)
    queue.add(2)
    for node in queue.iterator():
        print(node.start, node.end)
