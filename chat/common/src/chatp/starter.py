from logging import DEBUG
from functools import partial
from types import FrameType
from typing import Callable, Optional, Union, Coroutine, AsyncGenerator, Any
from contextlib import contextmanager, asynccontextmanager
from inspect import iscoroutinefunction

from asyncio import Future as AsyncIOFuture, get_running_loop, run as AsyncIORun

from .utils.uuid import get_or_create_instance_id
from .multiprocess.base import BaseWorkerProcess
from .multiprocess.process import ProcessManager, VirtualProcessManager
from .entrypoint import AsyncMultiProcessManager, AsyncSingleProcessManager
from .manager.service import ServiceManager
from .manager.grpc_client import GrpcClientManager
from .proto.processes.event_pb2 import Event as ProcEvent


def run_multiple(
    worker_factory: Callable,
    proc: BaseWorkerProcess,
    grpc_client: GrpcClientManager,
    app_setting: Optional[dict],
) -> None:
    if iscoroutinefunction(worker_factory):
        AsyncIORun(worker_factory(proc, grpc_client, app_setting))
    else:
        worker_factory(proc, grpc_client, app_setting)  # internally, uvicorn.run


async def run_single(
    worker_factory: Callable[[str], Union[Coroutine[Any, Any, None], Any]],
    proc: BaseWorkerProcess,
    grpc_client: GrpcClientManager,
    app_setting: Optional[dict],
) -> None:
    if iscoroutinefunction(worker_factory):
        await worker_factory(proc, grpc_client, app_setting)  # bind_addr, grpc_gateway
    else:
        # TODO Check: two loops share one service_queue
        # TODO Bug: grpcio Resource temporarily unavailable
        loop = get_running_loop()
        proc_manager: VirtualProcessManager = proc.proc_manager
        proc_manager.service_queue.bind_sender_loop(loop)
        proc_manager.proc_recv_queue.bind_receiver_loop(loop)
        await loop.run_in_executor(None, worker_factory, proc, grpc_client, app_setting)


@contextmanager
def reserve_port(port: int = 0):
    from socket import (
        socket,
        SOL_SOCKET,
        AF_INET,
        SOCK_STREAM,
        SO_REUSEADDR,
        SO_REUSEPORT,
    )

    sock = socket(AF_INET, SOCK_STREAM)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

    sock.setsockopt(SOL_SOCKET, SO_REUSEPORT, 1)
    if sock.getsockopt(SOL_SOCKET, SO_REUSEPORT) == 0:
        raise RuntimeError("Failed to set SO_REUSEPORT.")

    sock.set_inheritable(True)
    sock.setblocking(False)

    sock.bind(("localhost", port))
    try:
        yield sock
    finally:
        sock.close()


@contextmanager
def create_starter(
    yaml_path: str,
    *,
    worker_factory: Callable[[str, tuple, dict], None],
    handle_exit: Union[
        Callable[[int, Optional[FrameType]], None], Callable[[AsyncIOFuture], Any]
    ],
    pre_fork: Callable[["ProcessManager", BaseWorkerProcess], None] = None,
    post_fork: Callable[["ProcessManager", BaseWorkerProcess], None] = None,
    user_event_handler: Optional[Callable[[ProcEvent], Coroutine]] = None,
) -> AsyncGenerator[AsyncMultiProcessManager | AsyncSingleProcessManager, None]:
    from yaml import safe_load

    with open(yaml_path, "r", encoding="utf8") as fs:
        config: dict = safe_load(fs)

        develop: dict = config["develop"]
        use_monitor = develop.get("use_monitor", False)
        if not use_monitor:
            monitor_child_port = 0
        else:
            monitor_child_port = develop.get("monitor_child_port", 42580)
        log_level = develop.get("log_level", DEBUG)

        etcd_setting: dict = config["etcd_setting"]
        registered_service_prefix: Optional[str] = etcd_setting.get(
            "registered_service_prefix"
        )
        discovered_service_prefix: Optional[str] = etcd_setting.get(
            "discovered_service_prefix"
        )
        include_services: Optional[list] = etcd_setting.get("include_services")
        if include_services is not None and not isinstance(include_services, list):
            raise RuntimeError("include_services must be a list.")

        ServiceManager.registered_service_prefix = registered_service_prefix
        ServiceManager.discovered_service_prefix = discovered_service_prefix
        ServiceManager.include_services = include_services

        proc_arch: dict = config["process_architecture"]
        workers = proc_arch["workers"]
        if workers <= 0 or not isinstance(workers, int):
            raise RuntimeError("Args `workers` must be positive integer.")
        if (single := proc_arch["single"]) and workers > 1:
            raise RuntimeError("error: single = True but workers > 1.")
        # needs_sync = proc_arch["needs_sync"]
        bidirectional = proc_arch["bidirectional"]

        local_server: dict = config["local_server"]
        service_name = local_server["service_name"]
        platform_id_path = local_server.get("platform_id_path", "./platform_id")

        app_setting: dict = config.get("app_setting")

    from uvicorn import Config

    config = Config(app=None, log_level=log_level)
    del config

    port = local_server["port"]
    with reserve_port(port) as sock:
        bind_addr = f"localhost:{sock.getsockname()[1]}"
        print(f"Binding to {bind_addr}")

        platform_id = get_or_create_instance_id(platform_id_path)
        service_manager = ServiceManager(platform_id, service_name, bind_addr)
        # used to receive load info from all worker processes

        if not single:  # corner case: single = False and workers = 1
            process_manager: ProcessManager = ProcessManager(
                worker_target=partial(
                    run_multiple,
                    worker_factory,
                    app_setting=app_setting,
                ),  # tight arrange
                num_workers=workers,
                sock_fd=sock.fileno(),
                bind_addr=bind_addr,
                platform_id=platform_id,
                server_label=service_name,
                bidirectional=bidirectional,
                # needs_sync=needs_sync,
                pre_fork=pre_fork,
                post_fork=post_fork,
                user_event_handler=user_event_handler,
            )
            process_manager.bind_before_enter_loop(monitor_child_port)
            process_manager.post_initialize()  # `load queue`
            process_manager.spawn_workers()  # create pipe

            async_starter = AsyncMultiProcessManager(
                app_setting,
                handle_exit,
                process_manager,
                service_manager,
                debug=True,
                use_monitor=use_monitor,
                monitor_child_port=monitor_child_port,
            )
        else:
            process_manager: VirtualProcessManager = VirtualProcessManager(
                partial(
                    run_single,
                    worker_factory,
                    app_setting=app_setting,
                ),  # tight arrange
                sock_fd=sock.fileno(),
                bind_addr=bind_addr,
                platform_id=platform_id,
                server_label=service_name,
                bidirectional=bidirectional,
                user_event_handler=user_event_handler,
            )
            process_manager.bind_before_enter_loop(monitor_child_port)
            if iscoroutinefunction(worker_factory):
                process_manager.post_initialize()  # `load queue`
            else:
                process_manager.set_multithread()

            async_starter = AsyncSingleProcessManager(
                app_setting,
                handle_exit=None,
                main_executor_complete_cb=handle_exit,
                process_manager=process_manager,
                service_manager=service_manager,
                debug=True,
                use_monitor=use_monitor,
                monitor_child_port=monitor_child_port,
            )

        yield async_starter


@asynccontextmanager
async def move_on_starter(
    async_starter: AsyncMultiProcessManager | AsyncSingleProcessManager,
):
    async with async_starter:
        try:
            yield async_starter
        except BaseException as exc:
            print(f"Found exception in AsyncStarter: {exc}")


def create_async_starter(
    workers: int,
    port: int = 0,
    *,
    single: bool = True,
    needs_sync: bool = False,
    bidirectional: bool = True,
    service_name: str,
    platform_id_path: str,
    service_manager_cls: type(ServiceManager),
    worker_factory: Callable[[str, tuple, dict], None],
    handle_exit: Union[
        Callable[[int, Optional[FrameType]], None], Callable[[AsyncIOFuture], Any]
    ],
    user_event_handler: Optional[Callable[[ProcEvent], Coroutine]] = None,
    pre_fork: Optional[Callable[["ProcessManager", BaseWorkerProcess], None]] = None,
    post_fork: Optional[Callable[["ProcessManager", BaseWorkerProcess], None]] = None,
    use_monitor: bool = False,
    monitor_child_port: int = 42580,
    log_level: int = DEBUG,
    app_setting: Optional[dict] = None,
):
    pass
