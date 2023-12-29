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

from chatp.manager.grpc_client import GrpcClientManager
from chatp.multiprocess.process import ProcessManager
from chatp.multiprocess.worker import WorkerProcess

# from cuckoo_filter import CuckooFilter


def post_fork(proc_manager: ProcessManager, worker: WorkerProcess):
    # from opentelemetry.exporter.jaeger.proto.grpc import JaegerExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.semconv.resource import ResourceAttributes
    from grpc import Compression

    from chatp.utils.telemetry import Telemetry
    from chatp.utils.uuid import generate

    # opentelemetry intialize
    resource = Resource.create(
        {
            ResourceAttributes.SERVICE_NAMESPACE: "ChatApp",
            ResourceAttributes.SERVICE_NAME: "HttpGateway",
            ResourceAttributes.SERVICE_VERSION: "v1.0.0",
            ResourceAttributes.SERVICE_INSTANCE_ID: generate(),
            ResourceAttributes.OS_NAME: "Ubuntu 22.04",
        }
    )
    # trace_exporter = JaegerExporter(collector_endpoint="localhost:14250", insecure=True)
    trace_exporter = OTLPSpanExporter(
        endpoint="localhost:4317", insecure=True, compression=Compression.Gzip
    )
    Telemetry().setup_telemetry_tracer_provider(
        resource, trace_exporter
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
    from concurrent.futures import ThreadPoolExecutor
    from blacksheep.server.application import Application

    from routes.user import login, query_user, register, confirm
    from routes.friend import friend_request, friend_confirm, get_friends
    from routes.chat import pull_inbox, pull_sessions

    from middlewares.allow_or_deny import AllowOrDenyMiddleware
    from middlewares.prometheus import use_prometheus_metrics
    from middlewares.auth import HttpAuthentication
    from middlewares.ratelimiter import RatelimitingMiddleware

    from utils.setting import ServerSetting
    from utils.helper import cpu_initializer
    from utils.background_tasks import BackgroundTaskManager
    from utils.service_ctx import ServicesRegisrationContext

    from rmq.service import RMQService
    from chatp.redis.client import RedisClient

    # os.sched_setaffinity(proc.pid, {(proc.process_seq + 6) % os.cpu_count()})

    app = Application()
    redis_client = RedisClient()
    rmq_service = RMQService(setting=app_setting)
    executor = ThreadPoolExecutor(max_workers=2, initializer=cpu_initializer)
    context = ServicesRegisrationContext(
        grpc_manager, rmq_service, redis_client, executor
    )

    # context.register_instance(executor, dispose_cb=executor_shutdown)
    context.register_instance(ServerSetting(app_setting))
    context.register_instance(
        BackgroundTaskManager(), dispose_cb=BackgroundTaskManager.close
    )
    app.on_start += context.initialize
    app.on_stop += context.dispose

    # in fact, decorator not middleware
    http_auth = HttpAuthentication(grpc_manager, app)
    auth_token = http_auth.auth_token
    auth_metric = http_auth.auth_metrics

    rate_limiter = RatelimitingMiddleware(redis_client, app)
    ip_limiter = rate_limiter.ip_limiter  # simple anti-DDOS
    api_limiter = rate_limiter.api_limiter

    add_post = app.router.add_post
    add_get = app.router.add_get

    # middleware register <- PS: reversed
    app.middlewares.append(AllowOrDenyMiddleware(redis_client, app))  # ip filter
    use_prometheus_metrics(app, auth_decorator=auth_metric)

    # ---------------- user endpoint
    add_post(
        "/user/login",
        ip_limiter(
            api_limiter(login, capacity=1024, rate=512),
            trace_cycle=60,
            trace_threshold=5,
        ),  # 1req/3s, 5try/60s then blocked 10min
    )
    add_post(
        "/user/register",
        ip_limiter(
            api_limiter(register, capacity=1024, rate=256),
            trace_cycle=60,
            trace_threshold=5,
            blocked_time=86400,
        ),  # 1req/3s, 5times/60s then blocked 1day
    )

    add_get("/user/register/confirm/{token}", confirm)

    add_post(
        "/user/query_user",
        auth_token(
            ip_limiter(
                api_limiter(query_user, capacity=1024, rate=512),
                trace_cycle=60,
                trace_threshold=15,
                blocked_time=300,
            )  # 1req/3s 15req/60s then blocked 5min
        ),
    )

    # ---------------- friend endpoint
    add_post(
        "/friend/friend_request",
        auth_token(
            ip_limiter(
                api_limiter(friend_request, capacity=1024, rate=256),
                sliding_window=5,
                trace_cycle=60,
                trace_threshold=10,
                blocked_time=3600,
            )  # 1req/5s, 10times/90s then blocked 1h
        ),
    )

    add_post(
        "/friend/friend_confirm",
        auth_token(
            ip_limiter(
                api_limiter(friend_confirm, capacity=1024, rate=256),
                sliding_window=5,
                trace_cycle=60,
                trace_threshold=10,
                blocked_time=3600,
            )  # 1req/5s, 10times/90s then blocked 1h
        ),
    )
    add_get("/friend/friend_list", auth_token(get_friends))

    # ---------------- chat endpoint
    add_post("/chat/pull_inbox", auth_token(pull_inbox))
    add_post("/chat/pull_sessions", auth_token(pull_sessions))

    import uvicorn
    from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

    app = OpenTelemetryMiddleware(app)
    # uvicorn.run(app, fd=proc.proc_manager.sock_fd, log_level="debug")
    config = uvicorn.Config(app, fd=proc.proc_manager.sock_fd)
    await uvicorn.Server(config).serve()
