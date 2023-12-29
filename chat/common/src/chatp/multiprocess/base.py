from os import getpid
from enum import IntEnum
from time import monotonic
from collections import OrderedDict
from weakref import ref, ReferenceType
from typing import Any, Coroutine, Optional, Callable

from asyncio import Queue as AsyncIOQueue

from ..proto.processes.event_pb2 import Event as ProcEvent
from ..utils.model import ThreadsafeAsyncQueue


class ProcessState(IntEnum):
    Ready = 0
    Running = 1
    Dirty = 2
    AlreadyDone = 3


READY = ProcessState.Ready
RUNNING = ProcessState.Running
DIRTY = ProcessState.Dirty
DONE = ProcessState.AlreadyDone


class BaseProcessManager:
    work_mode: bool
    bidirectional: bool

    bind_addr: str
    sock_fd: int
    main_pid: int

    platform_id: str
    instance_id: int
    server_label: str

    proc_recv_queue: AsyncIOQueue | ThreadsafeAsyncQueue  # load info
    # seq: WorkerProcess
    processes: OrderedDict[int, "BaseWorkerProcess"] | tuple["BaseWorkerProcess"]

    is_multithread: bool = False  # used by VirtualWorkerProcess

    def __init__(
        self,
        bind_addr: str,
        sock_fd: int,
        *,
        platform_id: str,
        server_label: str,
        bidirectional: bool,
    ):
        self.bind_addr = bind_addr
        self.sock_fd = sock_fd
        self.platform_id = platform_id
        self.server_label = server_label
        self.bidirectional = bidirectional

        self.main_pid = getpid()

    def bind_before_enter_loop(self, monitor_child_port: int, **kwargs):
        self.monitor_child_port = monitor_child_port
        self.__dict__.update(kwargs)

    def post_initialize(self):
        ...

    async def dispatch_event(self, event: ProcEvent):
        ...


class BaseWorkerProcess:
    service_queue: AsyncIOQueue | ThreadsafeAsyncQueue

    __slots__ = (
        "name",
        "state",
        "spawn_time",
        "process_version",
        "proc_manager_weakref",
        "service_queue",
        "feed_data",
        "feed_data_nowait",
    )

    def __init__(
        self,
        name: str,
        process_version: str,
        proc_manager: BaseProcessManager,
    ):
        self.state = READY

        self.name = name
        self.process_version = process_version
        self.proc_manager_weakref: ReferenceType[BaseProcessManager] = ref(proc_manager)

        self.service_queue = None

    @property
    def age(self):
        return monotonic() - self.spawn_time

    @property
    def proc_manager(self) -> BaseProcessManager:
        return self.proc_manager_weakref()

    @property
    def bidirectional(self):
        return self.proc_manager.bidirectional

    def post_initialize(self):
        if self.bidirectional:
            queue: AsyncIOQueue[bytes] = AsyncIOQueue()  # services is finite
            self.service_queue = queue
            self.feed_data = queue.put  # service_manager put bytes into here
            self.feed_data_nowait = queue.put_nowait  # statistic_manager put into

    async def main_proc_task(self, reader_queue: AsyncIOQueue):
        ...

    async def interact_with_master(
        self,
        client_write_cb: Callable[[Any], Coroutine],
        event_handler: Optional[Callable[[ProcEvent], Coroutine]] = None,
    ):
        ...
