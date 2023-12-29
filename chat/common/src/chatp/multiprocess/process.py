from os import wait4, WNOHANG
from struct import pack
from logging import getLogger
from functools import partial
from itertools import repeat
from collections import OrderedDict
from operator import attrgetter
from types import MethodType
from typing import Callable, Optional, Coroutine, Any

from psutil import NoSuchProcess
from resource import getrusage, RUSAGE_SELF

# from memory_profiler import profile
from multiprocessing import get_context

from aiomisc.service import Service
from asyncio import (
    Queue as AsyncIOQueue,
    Task,
    CancelledError,
    sleep,
    wait,
    create_task,
    # get_running_loop,
    # to_thread,
)
from anyio import move_on_after

from .base import RUNNING, DIRTY, BaseProcessManager
from .worker import WorkerProcess, VirtualWorkerProcess
from .fork_wrapper import post_fork_wrapper
from ..utils.uuid import generate
from ..utils.model import ThreadsafeAsyncQueue
from ..proto.processes.event_pb2 import Event as ProcEvent

logger = getLogger("ProcessManager")
logger.setLevel(10)
MB_MULTIPLIER = 1024**2


def create_process_manager(
    bind_addr: str,
    platform_id: str,
    server_label: str,
    *,
    worker_target: Optional[Callable] = None,
    num_workers: int = -1,
    sock_fd: int = -1,
    **kwargs,
):
    if worker_target is None:
        return ProcessManager(
            worker_target,
            num_workers,
            sock_fd=sock_fd,
            bind_addr=bind_addr,
            platform_id=platform_id,
            server_label=server_label,
            **kwargs,
        )
    else:
        return VirtualProcessManager(
            bind_addr=bind_addr,
            platform_id=platform_id,
            server_label=server_label,
        )


class ProcessManager(BaseProcessManager, Service):
    work_mode: bool = True
    pause_delay: int = 10

    def __init__(
        self,
        worker_target,
        num_workers: int,
        *,
        sock_fd: int,
        bind_addr: str,
        platform_id: str,
        server_label: str,
        bidirectional: bool = True,
        # needs_sync: bool = False,
        user_event_handler: Optional[Callable[[ProcEvent], Coroutine]] = None,
        pre_fork: Callable[["ProcessManager", WorkerProcess], None] = None,
        post_fork: Callable[["ProcessManager", WorkerProcess], None] = None,
    ):
        # borrow ref from Gateway, used by child_proc
        super().__init__(
            bind_addr,
            sock_fd,
            platform_id=platform_id,
            server_label=server_label,
            bidirectional=bidirectional,
        )
        self.num_workers = num_workers

        self.worker_target = worker_target
        if post_fork is not None:
            post_fork = partial(post_fork, self)

        self._needs_discard: list[int] = []
        self._needs_schedule: list[WorkerProcess] = []
        self.processes: OrderedDict[int, WorkerProcess] = OrderedDict()
        self._processes_tasks_map: dict[WorkerProcess, Task] = {}

        context = get_context("fork")
        # shared_array = context.Array("B", 8) if needs_sync else None
        shared_array = context.Array("B", 8)
        self.worker_factory = partial(
            context.Process,
            target=post_fork_wrapper(
                worker_target,  # callable[BaseProcProcess, GrpcClientManager]
                post_fork=post_fork,
                user_event_handler=user_event_handler,
            ),
            daemon=True,
        )
        self._context = context
        self._shared_array = shared_array

        self.pre_fork = pre_fork
        self.post_fork = post_fork

        self.available_sequence = set(range(1, num_workers + 1))

    @property
    def shared_array(self):
        return self._shared_array

    def post_initialize(self):  # before 3.11, AsyncIOQueue needs a `loop` args
        self.proc_recv_queue = AsyncIOQueue()

    async def dispatch_event(self, data: ProcEvent):  # broadcast
        bytes_data = data.SerializeToString()
        bytes_length = len(bytes_data)
        data = pack(">B", bytes_length) + bytes_data
        for proc in filter(lambda proc: proc.state is RUNNING, self.processes.values()):
            await proc.feed_data(data)

    # @profile()
    def shutdown_workers(self):
        for process in self.processes.values():
            process.terminate()  # close child process
            process.join()
            # process.close_wpipe()  # parent write

    # TODO Ctrl-C will be captured by all processes
    async def wait_children_to_exit(self):
        processes = self.processes
        num_proc = len(processes)
        with move_on_after(10) as scope:
            try:
                while True:
                    exit_stat = wait4(-1, WNOHANG)
                    if exit_stat[0] == 0:
                        await sleep(0.5)
                    else:
                        logger.info("Found process exit with: %s", exit_stat)
                        num_proc -= 1
                        if num_proc == 0:
                            break
            except ChildProcessError as exc:
                logger.exception("Found exeption in `wait4`: %s", exc, exc_info=exc)
                return

        if scope.cancel_called:
            logger.warning("Main Process took too much time to wait children exit...")
            for process in processes.values():
                if process.is_alive():
                    process.kill(0)

    # @profile
    def spawn_workers(
        self, n: int = 0, needs_schedule_append: Optional[MethodType] = None
    ) -> None:
        n = n or self.num_workers
        processes = self.processes
        sequence_next = self.available_sequence.pop

        pre_fork = self.pre_fork
        worker_factory = self.worker_factory
        pipe_factory = (
            WorkerProcess.create_directional_pipe
            if self.bidirectional
            else WorkerProcess.create_unidirectional_pipe
        )

        name_prefix = f"WorkerProcess-{self.server_label}"
        for _ in repeat(None, n):
            seq_num = sequence_next()
            process = WorkerProcess(
                seq_num,
                name=f"{name_prefix}-{seq_num}",
                process_version=generate(5),  # 22B
                proc_manager=self,
            )
            processes[seq_num] = process
            if needs_schedule_append is not None:
                needs_schedule_append(process)

            if pre_fork is not None:
                pre_fork(self, process)

            process.spawn(worker_factory, args=(process,))
            process.post_initialize()
            process.bind_pipe(*pipe_factory())  # service_queue
            with process._child_pipe.detach():
                process.start()

            logger.info(f"successfully forked process: {process.name} [{process.pid}].")

    def reap_workers(self, needs_discard_append: MethodType):
        for proc in self.processes.values():
            if proc.is_alive():
                continue
            if proc.state is RUNNING:
                proc.state = DIRTY
                self._processes_tasks_map[proc].cancel()
            else:
                self._processes_tasks_map.pop(proc)

                process_seq = proc.process_seq
                needs_discard_append(process_seq)
                self.available_sequence.add(process_seq)

    def remove_workers(self):
        pass

    async def monitor(self):
        try:
            num_workers = self.num_workers
            processes = self.processes

            needs_discard = self._needs_discard
            needs_discard_append = needs_discard.append
            needs_discard_clear = needs_discard.clear

            needs_schedule = self._needs_schedule
            needs_schedule_append = needs_schedule.append
            needs_schedule_clear = needs_schedule.clear

            proc_recv_queue = self.proc_recv_queue
            tasks_map = self._processes_tasks_map
            schedule_task = (
                attrgetter("main_proc_task")
                if self.bidirectional
                else attrgetter("main_proc_task_undi")
            )

            reap_workers = self.reap_workers
            spawn_workers = self.spawn_workers
            remove_workers = self.remove_workers

            # main_proc = psutil.Process(self.main_pid)
            memory_usages = {}
            pause_delay = self.pause_delay
            while True:
                await sleep(pause_delay)
                # TODO pidfile

                reap_workers(needs_discard_append)
                if needs_discard:
                    for process_seq in needs_discard:
                        processes.pop(process_seq)
                    needs_discard_clear()

                if (n := num_workers - len(processes)) > 0:
                    spawn_workers(n, needs_schedule_append)
                    if needs_schedule:
                        tasks_map.update(
                            {
                                proc: create_task(schedule_task(proc)(proc_recv_queue))
                                for proc in needs_schedule
                            }
                        )
                        needs_schedule_clear()
                elif n < 0:
                    # TODO check load
                    remove_workers()
                else:
                    # memory_usages["main"] = main_proc.memory_info().rss / MB_MULTIPLIER
                    memory_usages["main"] = getrusage(RUSAGE_SELF).ru_maxrss / 1024
                    for seq, proc in processes.items():
                        try:
                            memory_usages[f"child-{seq}"] = (
                                proc._psutil_process.memory_info().rss / MB_MULTIPLIER
                            )
                        except NoSuchProcess:
                            # TODO process was forked successfully, but fastly exit due to some exc.
                            pass
                    logger.info(f"all worker processes are healthy: {memory_usages}")

                # master was promoted: maybe_promote_master()
        except CancelledError:
            logger.info("monitor_task completed.")

    async def start(self):
        proc_recv_queue = self.proc_recv_queue
        if self.bidirectional:
            self._processes_tasks_map = {
                proc: create_task(proc.main_proc_task(proc_recv_queue))
                for proc in self.processes.values()
            }
        else:
            self._processes_tasks_map = {
                proc: create_task(proc.main_proc_task_undi(proc_recv_queue))
                for proc in self.processes.values()
            }

        self.start_event.set()
        await self.monitor()

    async def stop(self, exc):
        if processes_tasks_map := self._processes_tasks_map:
            proc_tasks = processes_tasks_map.values()
            for task in proc_tasks:
                task.cancel()

            await wait(proc_tasks)


class VirtualProcessManager(BaseProcessManager):
    work_mode: bool = False

    def __init__(
        self,
        worker_target: Callable[[AsyncIOQueue], Coroutine[Any, Any, None]],
        *,
        sock_fd: int,
        bind_addr: str,
        platform_id: str,
        server_label: str,
        bidirectional: bool = True,
        user_event_handler: Optional[Callable[[ProcEvent], Coroutine]] = None,
    ):
        super().__init__(
            bind_addr,
            sock_fd,
            platform_id=platform_id,
            server_label=server_label,
            bidirectional=bidirectional,
        )
        self.worker_target = worker_target

        virtual_process = VirtualWorkerProcess(
            name=f"WorkerProcess-{server_label}",
            process_version=generate(5),  # 22B
            proc_manager=self,
        )
        virtual_process.start()
        self.vproc = virtual_process
        self.num_workers = 1
        self.processes = (virtual_process,)

        # roughly usage
        context = get_context("fork")
        # shared_array = context.Array("B", 8) if needs_sync else None
        self.shared_array = context.Array("B", 8)
        self.user_event_handler = user_event_handler

    @property
    def service_queue(self):
        return self.vproc.service_queue

    @service_queue.setter
    def service_queue(self, queue):
        self.vproc.service_queue = queue

    def post_initialize(self):
        self.vproc.post_initialize()  # service_queue: communicate with worker_target
        self.proc_recv_queue = AsyncIOQueue()  # load info from worker_target

    def set_multithread(self):  # needs to bind loops later
        assert self.work_mode is False
        self.is_multithread = True

        if self.bidirectional:
            vproc = self.vproc
            # TODO ReCheck: used by StatisticManager
            threadsafe_queue = ThreadsafeAsyncQueue()
            self.service_queue = threadsafe_queue
            vproc.feed_data = threadsafe_queue.put
            vproc.feed_data_nowait = threadsafe_queue.queue.put_nowait

        self.proc_recv_queue = ThreadsafeAsyncQueue()

    async def dispatch_event(self, data: ProcEvent):
        await self.vproc.feed_data(data)
