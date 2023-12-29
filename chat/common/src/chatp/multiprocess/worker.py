from errno import ESRCH
from signal import SIGINT
from struct import unpack
from time import monotonic
from logging import getLogger
from os import kill as osKill, close as osClose, getpid
from typing import AsyncContextManager, Coroutine, Optional, Callable

from psutil import Process as psutilProcess
from multiprocessing.process import BaseProcess

from asyncio import (
    Queue,
    StreamReader,
    StreamWriter,
    IncompleteReadError,
    CancelledError,
    create_task,
    get_running_loop,
)
from anyio import create_task_group
from aiopipe import aiopipe, aioduplex, AioDuplex

from .base import RUNNING, BaseWorkerProcess, BaseProcessManager
from ..utils.model import AsyncIOQueueWriterWrapper, ThreadsafeQueueWriterWrapper
from ..proto.processes.event_pb2 import Event as ProcEvent

logger = getLogger("WorkerProcess")
logger.setLevel(10)

class WorkerProcess(BaseWorkerProcess):
    _current_process: BaseProcess
    _psutil_process: psutilProcess

    __slots__ = (
        "process_seq",
        "_current_process",
        "_psutil_process",
        "_main_pipe",
        "_child_pipe",
    )

    def __init__(
        self,
        process_seq: int,
        *,
        name: str,
        process_version: str,
        proc_manager: BaseProcessManager,
    ):
        super().__init__(name, process_version, proc_manager)

        self.process_seq = process_seq
        self._current_process = self._psutil_process = None
        self._main_pipe = self._child_pipe = None

    @property
    def pid(self):
        return self._current_process.pid

    def bind_pipe(self, main_pipe: AioDuplex, child_pipe: AioDuplex):
        self._main_pipe, self._child_pipe = main_pipe, child_pipe

    def spawn(self, factory: Callable, args: tuple):
        self._current_process: BaseProcess = factory(name=self.name, args=args)

    def start(self):
        self._current_process.start()
        self._psutil_process = psutilProcess(self.pid)

        self.state = RUNNING
        self.spawn_time = monotonic()

    def kill(self, signo: int = SIGINT):
        try:
            osKill(self.pid, signo)
        except OSError as exc:
            if exc.errno == ESRCH:
                return False
        return True

    def join(self):
        self._current_process.join()

    def terminate(self):
        self._current_process.terminate()

    def is_alive(self):
        return self._current_process.is_alive()

    def close_child_pipe(self):
        if hasattr(self, "_child_pipe"):
            child_pipe = self._child_pipe
            try:
                osClose(child_pipe._rx._fd)
                osClose(child_pipe._tx._fd)
            except Exception as exc:
                # os.close(child_pipe._fd)  # undirectional pipe
                logger.info(exc)

    def close_main_pipe(self):
        if hasattr(self, "_main_pipe"):
            main_pipe = self._main_pipe
            try:
                osClose(main_pipe._rx._fd)
                osClose(main_pipe._tx._fd)
            except Exception as exc:
                # os.close(main_pipe._fd)  # undirectional pipe
                logger.info(exc)

    @staticmethod
    def create_unidirectional_pipe():
        return aiopipe()

    @staticmethod
    def create_directional_pipe():
        return aioduplex()

    async def recv_from_pipe(self):
        pass

    async def main_proc_task_undi(self, reader_queue: Queue):
        async_ctx_manager: AsyncContextManager[StreamReader] = self._main_pipe.open()
        async with async_ctx_manager as reader:
            try:
                reader_queue_put = reader_queue.put
                reader_readexactly = reader.readexactly
                while True:
                    size = await reader_readexactly(2)  # loadInfo: 2B length is enough
                    body = await reader_readexactly(unpack(">H", size)[0])
                    await reader_queue_put(body)  # LoadInfo
            except (IncompleteReadError, CancelledError):
                # IncompleteReadError means child proc shutdown
                # CancelledError means parent proc shutdown
                pass

    async def main_proc_task(self, reader_queue: Queue):
        async def _publish_event(writer: StreamWriter, queue: Queue):
            try:
                queue_get = queue.get
                writer_write, writer_drain = writer.write, writer.drain
                while True:
                    event: bytes = await queue_get()
                    writer_write(event)
                    await writer_drain()
            except CancelledError:
                logger.warning(f"Task<publish_event> was cancelled [{self.pid}]")
            except BaseException as exc:  # maybe worker process is closed
                logger.error(f"broken pipe, {exc}")

        async_ctx_manager: AsyncContextManager[
            tuple[StreamReader, StreamWriter]
        ] = self._main_pipe.open()

        async with async_ctx_manager as (reader, writer):
            publish_task = create_task(_publish_event(writer, self.service_queue))
            try:
                while True:
                    size = await reader.readexactly(2)  # loadInfo: 2B length is enough
                    body = await reader.readexactly(unpack(">H", size)[0])
                    await reader_queue.put(body)  # LoadInfo

            except (IncompleteReadError, CancelledError):
                # IncompleteReadError means child proc shutdown
                # CancelledError means parent proc shutdown
                if publish_task is not None:
                    publish_task.cancel()  # cancel publish task and ends main_proc_task
                    try:
                        await publish_task
                    except CancelledError:
                        pass
                    except BaseException as exc:
                        logger.info(f"unknown exception, {exc}")

    async def child_proc_task_undi(
        self, client_write_cb: Callable[[StreamWriter], None]
    ):
        async_ctx_manager: AsyncContextManager[StreamWriter] = self._child_pipe.open()
        async with async_ctx_manager as writer:
            await client_write_cb(writer)  # StatisticInfo To MainProc

    async def child_proc_task(
        self,
        client_write_cb: Callable[[StreamWriter], Coroutine],
        event_handler: Callable[[ProcEvent], Coroutine],
    ):
        async_ctx_manager: AsyncContextManager[
            tuple[StreamReader, StreamWriter]
        ] = self._child_pipe.open()

        async with async_ctx_manager as (reader, writer):
            proc_write_task = create_task(client_write_cb(writer))  # StatisticInfo
            try:
                while True:
                    size = await reader.readexactly(1)  # ProcEvent: 1B length is enough
                    body = await reader.readexactly(unpack(">B", size)[0])
                    event = ProcEvent.FromString(body)
                    await event_handler(event)
                    # yield body  # ServiceEvent or LoadHintInfo

            except (IncompleteReadError, CancelledError, GeneratorExit):
                proc_write_task.cancel()
                try:
                    await proc_write_task
                except CancelledError:
                    pass

    async def interact_with_master(
        self,
        client_write_cb: Callable[[StreamWriter], Coroutine],
        event_handler: Optional[Callable[[ProcEvent], Coroutine]] = None,
    ):
        if self.bidirectional:
            await self.child_proc_task(client_write_cb, event_handler)
        else:
            await self.child_proc_task_undi(client_write_cb)

    async def create_unix_server(self):
        pass

    async def recv_from_unix_socket(self):
        pass


class VirtualWorkerProcess(BaseWorkerProcess):
    __slots__ = "pid", "process_seq"

    def __init__(
        self,
        *,
        name: str,
        process_version: str,
        proc_manager: BaseProcessManager,
    ):
        super().__init__(name, process_version, proc_manager)
        self.process_seq = 0

        self.pid = getpid()

    def start(self):
        self.state = RUNNING
        self.spawn_time = monotonic()

    async def interact_with_master(
        self,
        client_write_cb: Callable[
            [AsyncIOQueueWriterWrapper | ThreadsafeQueueWriterWrapper], Coroutine
        ],
        event_handler: Optional[Callable[[ProcEvent], Coroutine]] = None,
    ):
        async with create_task_group() as tg:
            proc_manager = self.proc_manager

            # corresponds to VirtualProcessManager.set_multithread
            proc_recv_queue = proc_manager.proc_recv_queue
            if proc_manager.is_multithread:
                child_loop = get_running_loop()
                proc_recv_queue.bind_sender_loop(child_loop)
                queue_writer = ThreadsafeQueueWriterWrapper(proc_recv_queue)
            else:
                queue_writer = AsyncIOQueueWriterWrapper(proc_recv_queue)
            tg.start_soon(client_write_cb, queue_writer)  # load_queue

            if self.bidirectional:
                service_queue = self.service_queue
                if proc_manager.is_multithread:
                    service_queue.bind_receiver_loop(child_loop)

                queue_get = service_queue.get
                while True:
                    event = await queue_get()
                    await event_handler(event)
