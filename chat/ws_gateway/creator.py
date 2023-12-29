from socket import (
    socket,
    SOCK_STREAM,
    AF_INET,
    AF_INET6,
    SO_REUSEADDR,
    SO_REUSEPORT,
    SOL_SOCKET,
)
from typing import Optional

from chatp.multiprocess.worker import WorkerProcess
from chatp.multiprocess.process import ProcessManager
from chatp.manager.grpc_client import GrpcClientManager


def post_fork(proc_manager: ProcessManager, worker: WorkerProcess):
    # from opentelemetry.exporter.jaeger.proto.grpc import JaegerExporter
    from grpc import Compression
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.semconv.resource import ResourceAttributes
    from chatp.utils.telemetry import Telemetry

    resource = Resource.create(
        {
            ResourceAttributes.SERVICE_NAMESPACE: "ChatApp",
            ResourceAttributes.SERVICE_NAME: "WsGateway",
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
    # metric_exporter = OTLPMetricExporter(
    #     endpoint="localhost:5555", insecure=True, compression=grpc.Compression.Gzip
    # )
    Telemetry().setup_telemetry_tracer_provider(
        resource,
        trace_exporter,
        # metric_exporter,
    )  # needs closed when lifespan shutdown


def create_socket(
    bind: str,
    type_: int = SOCK_STREAM,
    reuser_port: bool = True,
) -> socket:
    bind = bind.replace("[", "").replace("]", "")
    try:
        value = bind.rsplit(":", 1)
        host, port = value[0], int(value[1])
    except (ValueError, IndexError):
        host, port = bind, 8000

    sock = socket(AF_INET6 if ":" in host else AF_INET, type_)
    if reuser_port:
        sock.setsockopt(SOL_SOCKET, SO_REUSEPORT, 1)
    sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

    sock.bind((host, port))
    sock.setblocking(False)
    sock.set_inheritable(True)
    return sock


async def create_worker(
    proc: WorkerProcess, grpc_manager: GrpcClientManager, app_setting: Optional[dict]
):
    from opentelemetry.instrumentation.starlette import StarletteInstrumentor
    from starlette.applications import Starlette
    from starlette.routing import WebSocketRoute
    import uvicorn

    from routes.ws import websocket_endpoint
    from lifespan import LifeSpan

    # import os
    # os.sched_setaffinity(proc.pid, {(proc.process_seq + 1) % os.cpu_count()})

    routes = [
        WebSocketRoute("/chatp", endpoint=websocket_endpoint),
    ]

    proc_manager: ProcessManager = proc.proc_manager
    app_setting["monitor_child_port"] = proc_manager.monitor_child_port
    app = Starlette(
        routes=routes,
        lifespan=LifeSpan(
            proc,
            grpc_manager,
            app_setting,
        ),
    )
    instrumentor = StarletteInstrumentor()
    instrumentor.instrument_app(app)  # inner: OpenTelemetryMiddleware, insert 0

    config = uvicorn.Config(app, fd=proc_manager.sock_fd)
    await uvicorn.Server(config).serve()
    # uvicorn.run(app, fd=proc_manager.sock_fd)
