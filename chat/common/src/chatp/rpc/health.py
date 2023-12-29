from typing import Callable, Coroutine
from asyncio import create_task

from grpc.aio._server import Server as AioServer
from grpc_health.v1._async import HealthServicer
from grpc_health.v1 import health_pb2_grpc
from grpc_health.v1.health_pb2 import HealthCheckRequest, HealthCheckResponse


SERVING = HealthCheckResponse.SERVING
NOT_SERVING = HealthCheckResponse.NOT_SERVING


def configure_health_server(
    server: AioServer, toggle_handler: Callable[[HealthServicer], Coroutine]
):
    health_servicer = HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    return create_task(toggle_handler(health_servicer))


async def health_check(stub: health_pb2_grpc.HealthStub, service: str):
    resp = await stub.Check(HealthCheckRequest(service=service))
    if (status := resp.status) is SERVING:
        pass
    elif status is NOT_SERVING:
        pass
