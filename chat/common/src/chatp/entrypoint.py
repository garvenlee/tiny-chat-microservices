from types import FrameType
from typing import Callable, Optional, Any
from concurrent.futures import ThreadPoolExecutor

from attrs import define, field

from aiomonitor import start_monitor, Monitor
from aiomisc import Entrypoint
from asyncio import (
    Task as AsyncIOTask,
    Future as AsyncIOFuture,
    get_running_loop,
    create_task,
    wait,
    wait_for,
)

from .utils.signals import install_signal_handlers
from .multiprocess.process import ProcessManager, VirtualProcessManager
from .manager.grpc_client import GrpcClientManager
from .manager.service import ServiceManager
from .manager.loadbalance import LoadBalancer
from .manager.statistic import StatisticManager
from .rpc.grpc_service import GrpcService


@define(slots=True)
class AsyncMultiProcessManager:
    app_setting: dict
    handle_exit: Callable[[int, FrameType], Any]

    process_manager: ProcessManager
    service_manager: ServiceManager
    statistic_manager: StatisticManager = field(factory=StatisticManager)

    debug: bool = False
    use_monitor: bool = False
    monitor: Optional[Monitor] = None
    monitor_child_port: Optional[int] = None
    console_locals: Optional[dict] = None

    _executor: ThreadPoolExecutor = field(
        factory=lambda: ThreadPoolExecutor(max_workers=4)
    )
    _entrypoint: Optional[Entrypoint] = None
    # _exitstack: AsyncExitStack = field(factory=AsyncExitStack)

    @property
    def executor(self):
        return self._executor

    def __attrs_post_init__(self):
        # self.process_manager.bind_before_enter_loop(self.monitor_child_port)

        service_manager = self.service_manager
        service_manager.is_single = False

        statistic_manager = self.statistic_manager
        statistic_manager.use_discovery = service_manager.use_discovery
        statistic_manager.work_mode = True

    async def __aenter__(self) -> "AsyncMultiProcessManager":
        loop = get_running_loop()
        if self.debug:
            loop.set_debug(True)

        loop.set_default_executor(self._executor)

        process_manager = self.process_manager
        # before 3.11, Queue & aiopipe must be created in a coroutine
        # process_manager.post_initialize()  # `load queue`
        # process_manager.spawn_workers()  # create pipe

        service_manager = self.service_manager
        service_manager.bind(process_manager.dispatch_event)

        processes = process_manager.processes
        statistic_manager = self.statistic_manager
        # used to receive load info from all worker processes
        statistic_manager.bind_queue(process_manager.proc_recv_queue)
        statistic_manager.bind_workers(processes)

        entrypoint = Entrypoint(
            process_manager, service_manager, statistic_manager, loop=loop
        )
        self._entrypoint = entrypoint

        try:
            await entrypoint.start_services(
                process_manager, service_manager, statistic_manager
            )
        except BaseException as exc:
            await self.__aexit__(exc.__class__, exc, exc.__traceback__)
            raise

        # mainloop - statistic
        if self.use_monitor:
            self.monitor = monitor = start_monitor(loop)
            self.console_locals = console_locals = monitor.console_locals

            console_locals["procs"] = processes
            console_locals["services"] = service_manager.cache
            console_locals["statistic"] = statistic_manager.name_map_usages

        print(
            "[Entrypoint] Main Process has already initialized, now begin to initialize work processes"
        )
        process_manager.shared_array[-1] = 1  # sync point: main proc initialized
        install_signal_handlers(self.handle_exit)
        return self

    async def close_entrypoint(self, exc: BaseException):
        entrypoint = self._entrypoint
        if tasks := entrypoint._tasks:
            to_cancel = list(tasks)  # maybe certain start_task doesnt ends
            for task in to_cancel:
                task.cancel()

            pending, _ = await wait(to_cancel)
            done, _ = await wait(
                [create_task(srv.stop(exc)) for srv in entrypoint.services]
            )
            done.update(pending)
        else:
            done, _ = await wait(
                [create_task(srv.stop(exc)) for srv in entrypoint.services]
            )

        exceptions = []
        for fut in done:
            if (exc := fut._exception) is not None:
                exceptions.append(exc)
        return exceptions

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        print("[Entrypoint] Main Process is ready to exit")
        exceptions = await self.close_entrypoint(exc_val)

        if (monitor := self.monitor) is not None:
            self.monitor = monitor
            self.console_locals = None
            try:
                monitor.close()
            except BaseException as exc:
                exceptions.append(exc)

        self._executor.shutdown(wait=False)

        print("[Entrypoint] Main Process waits work processes to exit now...")
        await self.process_manager.wait_children_to_exit()
        if exceptions:
            raise BaseExceptionGroup("Aggregated Exceptions", exceptions)


@define(slots=True)
class AsyncSingleProcessManager:
    app_setting: dict

    handle_exit: Callable[[int, FrameType], Any]
    main_executor_complete_cb: Callable[[AsyncIOFuture], Any]

    process_manager: VirtualProcessManager
    service_manager: ServiceManager
    statistic_manager: StatisticManager = field(factory=StatisticManager)

    debug: bool = False
    use_monitor: bool = False
    monitor: Optional[Monitor] = None
    monitor_child_port: Optional[int] = None
    console_locals: Optional[dict] = None

    grpc_manager: Optional[GrpcClientManager] = None
    _target_task: Optional[AsyncIOTask] = None
    _executor: ThreadPoolExecutor = field(
        factory=lambda: ThreadPoolExecutor(max_workers=4)
    )
    _entrypoint: Optional[Entrypoint] = None
    # _exitstack: AsyncExitStack = field(factory=AsyncExitStack)

    @property
    def executor(self):
        return self._executor

    def __attrs_post_init__(self):
        service_manager = self.service_manager
        service_manager.is_single = True

        statistic_manager = self.statistic_manager
        statistic_manager.use_discovery = service_manager.use_discovery
        statistic_manager.work_mode = False

    async def __aenter__(self) -> "AsyncSingleProcessManager":
        loop = get_running_loop()
        if self.debug:
            loop.set_debug(True)

        loop.set_default_executor(self._executor)

        if (handle_exit := self.handle_exit) is not None:
            install_signal_handlers(handle_exit, loop)

        process_manager = self.process_manager
        # process_manager.post_initialize()

        # TODO target's load info, how to convey back to statistic_manager
        statistic_manager = self.statistic_manager
        statistic_manager.bind_queue(process_manager.proc_recv_queue)

        service_manager = self.service_manager
        service_manager.bind(process_manager.dispatch_event)  # publish service

        entrypoint = Entrypoint(service_manager, statistic_manager, loop=loop)
        self._entrypoint = entrypoint

        try:
            await entrypoint.start_services(service_manager, statistic_manager)
        except BaseException as exc:
            await self.__aexit__(exc.__class__, exc, exc.__traceback__)
            raise
        else:
            # In AsyncMultiProcessManager, grpc_manager is created in post_fork_wrapper
            # this part is moved before entrypoint.start_services, in order to decide
            # virtualWorkerProcess.is_multithread
            load_manager = LoadBalancer(GrpcService.services)
            grpc_manager = GrpcClientManager(
                multi_work_mode=False,
                bidirectional=process_manager.bidirectional,
            )

            vproc = process_manager.vproc
            grpc_manager.post_initialize(
                vproc,
                load_manager,
                user_handler=process_manager.user_event_handler,
            )
            self.grpc_manager = grpc_manager

            target_task = loop.create_task(
                process_manager.worker_target(vproc, grpc_client=grpc_manager)
            )
            if (complete_cb := self.main_executor_complete_cb) is not None:
                target_task.add_done_callback(complete_cb)
            self._target_task = target_task

            # mainloop - statistic
            if self.use_monitor:
                self.monitor = monitor = start_monitor(loop)
                self.console_locals = console_locals = monitor.console_locals

                console_locals["services"] = service_manager.cache
                console_locals["statistic"] = statistic_manager.name_map_usages
            return self

    async def close_entrypoint(self, exc: BaseException):
        entrypoint = self._entrypoint
        if tasks := entrypoint._tasks:
            to_cancel = list(tasks)  # maybe certain start_task doesnt ends
            for task in to_cancel:
                task.cancel()

            pending, _ = await wait(to_cancel)
            done, _ = await wait(
                [create_task(srv.stop(exc)) for srv in entrypoint.services]
            )
            done.update(pending)
        else:
            done, _ = await wait(
                [create_task(srv.stop(exc)) for srv in entrypoint.services]
            )

        exceptions = []
        for fut in done:
            if (exc := fut._exception) is not None:
                exceptions.append(exc)
        return exceptions

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        raise_exc = None
        if (target_task := self._target_task) is not None:
            self._target_task = None
            target_task.cancel()
            try:
                await wait_for(target_task, timeout=10),
            except BaseException as exc:
                raise_exc = exc

        exceptions = await self.close_entrypoint(exc_val)
        if raise_exc is not None:
            exceptions.append(raise_exc)

        if (monitor := self.monitor) is not None:
            self.monitor = None
            self.console_locals = None
            try:
                monitor.close()
            except BaseException as exc:
                exceptions.append(exc)

        if exceptions:
            raise BaseExceptionGroup("Aggregated Exceptions", exceptions)
