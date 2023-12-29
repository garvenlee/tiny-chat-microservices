from logging import getLogger, DEBUG
from types import FrameType
from typing import Optional
from contextlib import AsyncExitStack
from concurrent.futures import ThreadPoolExecutor
from asyncio import get_running_loop

from chatp.manager.grpc_client import GrpcClientManager
from chatp.multiprocess.process import ProcessManager
from chatp.multiprocess.worker import WorkerProcess
from chatp.utils.signals import install_signal_handlers


logger = getLogger("PushService")


def post_fork(proc_manager: ProcessManager, worker: WorkerProcess):
    # from opentelemetry.exporter.jaeger.proto.grpc import JaegerExporter

    from grpc import Compression
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.semconv.resource import ResourceAttributes
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from chatp.utils.telemetry import Telemetry

    from uvicorn import Config

    config = Config(app=None, log_level=DEBUG)
    del config

    resource = Resource.create(
        {
            ResourceAttributes.SERVICE_NAMESPACE: "ChatApp",
            ResourceAttributes.SERVICE_NAME: "PushService",
            ResourceAttributes.SERVICE_VERSION: "v1.0.0",
            ResourceAttributes.SERVICE_INSTANCE_ID: proc_manager.platform_id,
            ResourceAttributes.OS_NAME: "Ubuntu 22.04",
            "worker": worker.pid,
        }
    )
    # exporter = JaegerExporter(collector_endpoint="localhost:14250", insecure=True)
    trace_exporter = OTLPSpanExporter(
        endpoint="localhost:4317", insecure=True, compression=Compression.Gzip
    )
    Telemetry().setup_telemetry_tracer_provider(
        resource, trace_exporter
    )  # needs closed when lifespan shutdown


async def serve(
    proc: WorkerProcess, grpc_manager: GrpcClientManager, app_setting: Optional[dict]
) -> None:
    del grpc_manager

    from grpc.aio import server as grpc_aio_server
    from opentelemetry.instrumentation.grpc import aio_server_interceptor
    from chatp.proto.services.push.push_pb2_grpc import add_PushServicer_to_server
    from chatp.redis.client import RedisClient
    from rmq.service import RMQService
    from push_service import PushServicer

    loop = get_running_loop()
    loop.set_debug(True)
    executor = ThreadPoolExecutor(max_workers=4)
    loop.set_default_executor(executor)
    create_task = loop.create_task

    async with AsyncExitStack() as exitstack:
        server = grpc_aio_server(
            interceptors=[aio_server_interceptor()],
            options=[
                ("grpc.keepalive_time_ms", 20000),
                ("grpc.keepalive_timeout_ms", 10000),
                ("grpc.http2.min_ping_interval_without_data_ms", 5000),
                #   ('grpc.max_connection_idle_ms', 10000),
                #   ('grpc.max_connection_age_ms', 30000),
                #   ('grpc.max_connection_age_grace_ms', 5000),
                ("grpc.http2.max_pings_without_data", 5),
                ("grpc.keepalive_permit_without_calls", 1),
            ],
            maximum_concurrent_rpcs=4096,
        )
        rmq_backend = RMQService(app_setting)
        redis_client = RedisClient()

        push_servicer = PushServicer(redis_client=redis_client, loop=loop)
        add_PushServicer_to_server(servicer=push_servicer, server=server)
        server.add_insecure_port(proc.proc_manager.bind_addr)

        logger.info("Begin to start RMQService, RedisClient...")
        await exitstack.enter_async_context(redis_client)
        await exitstack.enter_async_context(rmq_backend)  # firstly exit
        rmq_task = create_task(rmq_backend.run(push_servicer.consume_event))

        logger.info("Begin to start grpc server...")
        await server.start()
        logger.info("Server is listening...")

        def handle_exit(sig: int, frame: Optional[FrameType]):
            logger.info(
                f"GrpcServer captured signal {sig}, then would do some clear work"
            )
            nonlocal closed
            if not closed:
                closed = True
                rmq_task.cancel()
                rmq_task.add_done_callback(lambda _: create_task(server.stop(5)))

        closed = False
        install_signal_handlers(handle_exit)
        await server.wait_for_termination()
        logger.info("GrpcServer has shutdown, begin to clear AsyncExitStack...")

    logger.info("Main Worker exited successfully!")
