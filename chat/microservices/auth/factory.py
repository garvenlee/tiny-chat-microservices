import logging
from types import FrameType
from typing import Optional
from functools import partial
from contextlib import AsyncExitStack
from concurrent.futures import ThreadPoolExecutor

from asyncio import get_running_loop

from grpc.aio import server as grpc_aio_server
from opentelemetry.instrumentation.grpc import aio_server_interceptor

from chatp.manager.grpc_client import GrpcClientManager
from chatp.multiprocess.process import ProcessManager
from chatp.multiprocess.worker import WorkerProcess
from chatp.proto.services.auth.auth_user_pb2_grpc import add_AuthUserServicer_to_server
from chatp.redis.client import RedisClient
from chatp.utils.signals import install_signal_handlers

logger = logging.getLogger("AuthServer")


def post_fork(proc_manager: ProcessManager, worker: WorkerProcess):
    # from opentelemetry.exporter.jaeger.proto.grpc import JaegerExporter
    from grpc import Compression
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.semconv.resource import ResourceAttributes
    from chatp.utils.telemetry import Telemetry

    resource = Resource.create(
        {
            ResourceAttributes.SERVICE_NAMESPACE: "ChatApp",
            ResourceAttributes.SERVICE_NAME: "AuthService",
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


async def serve(
    proc: WorkerProcess, grpc_manager: GrpcClientManager, app_setting: Optional[dict]
) -> None:
    from algo.backend import AuthBackend
    from algo.config import Configuraton
    from rpc.user_service import UserService
    from auth_service import AuthService
    from auth_handler import retrieve_refresh_token, store_refresh_token

    del app_setting

    # os.sched_setaffinity(proc.pid, {(proc.process_seq + 2) % os.cpu_count()})
    # from rpc.redis_service import RedisService

    loop = get_running_loop()
    executor = ThreadPoolExecutor(max_workers=4)
    loop.set_default_executor(executor)
    async with AsyncExitStack() as exitstack:
        redis_client = RedisClient()
        await exitstack.enter_async_context(redis_client)
        await exitstack.enter_async_context(grpc_manager)
        # redis_stub_getter = partial(grpc_manager.get, "RedisService")
        redis_get_func = redis_client.redis_get
        redis_set_func = redis_client.redis_set
        config = Configuraton(
            store_refresh_token=partial(
                store_refresh_token,
                # redis_set=redis_stub_getter,
                redis_set=redis_set_func,
            ),
            retrieve_refresh_token=partial(
                retrieve_refresh_token,
                # redis_get=redis_stub_getter,
                redis_get=redis_get_func,
            ),
        )
        auth_backend = AuthBackend(config, loop=loop)
        service = AuthService(
            grpc_manager,
            auth_backend,
            loop=loop,
        )

        server_options = [
            ("grpc.keepalive_time_ms", 20000),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.http2.min_ping_interval_without_data_ms", 5000),
            #   ('grpc.max_connection_idle_ms', 10000),
            #   ('grpc.max_connection_age_ms', 30000),
            #   ('grpc.max_connection_age_grace_ms', 5000),
            ("grpc.http2.max_pings_without_data", 5),
            ("grpc.keepalive_permit_without_calls", 1),
        ]
        server = grpc_aio_server(
            interceptors=[aio_server_interceptor()],
            options=server_options,
            maximum_concurrent_rpcs=4096,
        )
        add_AuthUserServicer_to_server(service, server)
        server.add_insecure_port(proc.proc_manager.bind_addr)

        logger.info("begin to start grpc server...")
        await server.start()

        logger.info("grpc server is listening")

        def handle_exit(sig: int, frame: Optional[FrameType]):
            logger.info("begin to shutdown server")
            loop.create_task(server.stop(5))

        install_signal_handlers(handle_exit)
        await server.wait_for_termination()
        logger.info("server has shutdown")
