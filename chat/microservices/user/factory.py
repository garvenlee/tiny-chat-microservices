from typing import Optional
from types import FrameType

from contextlib import AsyncExitStack
from concurrent.futures import ThreadPoolExecutor
from asyncio import get_running_loop


from chatp.manager.grpc_client import GrpcClientManager
from chatp.multiprocess.process import ProcessManager
from chatp.multiprocess.worker import WorkerProcess
from chatp.utils.signals import install_signal_handlers


def post_fork(proc_manager: ProcessManager, worker: WorkerProcess):
    # from opentelemetry.exporter.jaeger.proto.grpc import JaegerExporter
    from grpc import Compression
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.semconv.resource import ResourceAttributes
    from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from chatp.utils.telemetry import Telemetry

    resource = Resource.create(
        {
            ResourceAttributes.SERVICE_NAMESPACE: "ChatApp",
            ResourceAttributes.SERVICE_NAME: "UserService",
            ResourceAttributes.SERVICE_VERSION: "v1.0.0",
            ResourceAttributes.SERVICE_INSTANCE_ID: proc_manager.platform_id,
            ResourceAttributes.OS_NAME: "Ubuntu 22.04",
            "worker": worker.pid,
        }
    )

    # trace_exporter = JaegerExporter(collector_endpoint="localhost:14250", insecure=True)
    trace_exporter = OTLPSpanExporter(
        endpoint="localhost:4317", insecure=True, compression=Compression.Gzip
    )

    Telemetry().setup_telemetry_tracer_provider(
        resource, trace_exporter
    )  # needs closed when lifespan shutdown

    AsyncPGInstrumentor().instrument()  # special in UserService


async def serve(
    proc: WorkerProcess, grpc_manager: GrpcClientManager, app_setting: Optional[dict]
) -> None:
    from logging import getLogger
    from db_service import DbService  # asyncpg object consumes 80MB
    from user_servicer import UserServicer
    from friend_servicer import FriendServicer
    from chatp.proto.services.user.user_pb2_grpc import add_UserServicer_to_server
    from chatp.proto.services.friend.friend_pb2_grpc import add_FriendServicer_to_server

    from grpc.aio import server as grpc_aio_server
    from opentelemetry.instrumentation.grpc import aio_server_interceptor

    del grpc_manager
    del app_setting

    # import os
    # os.sched_setaffinity(proc.pid, {(proc.process_seq + 4) % os.cpu_count()})
    # worker_pid = os.getpid()

    loop = get_running_loop()
    loop.set_debug(True)
    executor = ThreadPoolExecutor(max_workers=4)
    loop.set_default_executor(executor)

    logger = getLogger("ServerFactory")
    async with AsyncExitStack() as exitstack:
        db_service = DbService(password="121380316", min_size=5)
        db_executor = db_service.executor

        logger.info("Begin to start db_service...")
        await exitstack.enter_async_context(db_service)
        logger.info("DbService is active now.")

        server = grpc_aio_server(
            interceptors=[aio_server_interceptor()],
            options=[
                ("grpc.keepalive_time_ms", 20000),  # 20s ping
                ("grpc.keepalive_timeout_ms", 10000),  # 10s wait ping
                (
                    "grpc.keepalive_permit_without_calls",
                    1,
                ),  # send ping though no active rpcs
                ("grpc.http2.min_ping_interval_without_data_ms", 5000),
                ("grpc.http2.max_pings_without_data", 5),
                # ('grpc.max_connection_idle_ms', 10000),
                # ('grpc.max_connection_age_ms', 30000),
                # ('grpc.max_connection_age_grace_ms', 5000),
            ],
            maximum_concurrent_rpcs=4096,
        )
        add_UserServicer_to_server(
            servicer=UserServicer(executor=db_executor, loop=loop),
            server=server,
        )
        add_FriendServicer_to_server(
            servicer=FriendServicer(db_executor), server=server
        )
        server.add_insecure_port(proc.proc_manager.bind_addr)

        logger.info("Begin to start grpc server...")
        await server.start()
        logger.info("Server is listening...")

        def handle_exit(sig: int, frame: FrameType):
            nonlocal closed
            logger.info(f"> Catched signal {sig} from os signal")
            if not closed:
                closed = True
                loop.create_task(server.stop(5))

        closed = False
        install_signal_handlers(handle_exit)
        await server.wait_for_termination()
        executor.shutdown(wait=False)
        logger.info("Server has shutdown.")
