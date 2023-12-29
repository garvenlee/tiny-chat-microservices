from os import getpid
from threading import get_ident
from asyncio import (
    Queue,
    Lock,
    BaseEventLoop,
    run_coroutine_threadsafe,
)

from cassandra.connection import Connection
from cassandra.io.asyncioreactor import AsyncioConnection as AsyncioBaseConnection


class DummyThread:
    __slots__ = "_ident"

    def __init__(self):
        self._ident = get_ident()

    @property
    def ident(self):
        return self._ident


class AsyncioConnection(AsyncioBaseConnection):
    def __init__(self, *args, **kwargs):
        Connection.__init__(self, *args, **kwargs)

        self._connect_socket()  # blocking call: sock.connect
        self._socket.setblocking(False)

        # Python3.11 already removed `loop` input args`
        self._write_queue = Queue()
        self._write_queue_lock = Lock()

        # see initialize_reactor -- loop is running in a separate thread, so we
        # have to use a threadsafe call
        self._read_watcher = run_coroutine_threadsafe(
            self.handle_read(), loop=self._loop
        )
        self._write_watcher = run_coroutine_threadsafe(
            self.handle_write(), loop=self._loop
        )

        # non-blocking call: send_msg -> push, but asynchronous
        self._send_options_message()

    @classmethod
    def before_initialize_reactor(cls, loop: BaseEventLoop):
        # can be only used in a running asyncio-based-loop thread
        cls._loop = loop
        cls._loop_thread = DummyThread()

    @classmethod
    def initialize_reactor(cls):
        with cls._lock:
            if cls._pid != getpid():
                print("`initialize_reactor` is called in another process.")

    async def _push_msg(self, chunks):
        async with self._write_queue_lock:
            for chunk in chunks:
                self._write_queue.put_nowait(chunk)
