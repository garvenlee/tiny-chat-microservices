import logging
from types import FrameType
from typing import Optional
from contextlib import AsyncExitStack
from asyncio import get_running_loop

from chatp.multiprocess.worker import WorkerProcess
from chatp.manager.grpc_client import GrpcClientManager
from chatp.utils.signals import install_signal_handlers

logger = logging.getLogger("UpstreamTransferService")
logger.setLevel(10)


async def serve(
    proc: WorkerProcess, grpc_manager: GrpcClientManager, app_setting: Optional[dict]
) -> None:
    from grpc.aio import server as grpc_aio_server
    from chatp.proto.services.transfer.upstream_pb2_grpc import (
        add_UpstreamTransferServicer_to_server,
    )
    from rmq.service import RMQService
    from upstream_service import UpstreamTransferServicer

    async with AsyncExitStack() as exitstack:
        # First, initialize grpc client
        await exitstack.enter_async_context(grpc_manager)

        # Second, initialize rmq_service
        app_setting["PLATFORM_ID"] = proc.proc_manager.platform_id
        rmq_service = RMQService(app_setting)
        servicer = UpstreamTransferServicer(
            grpc_manager, rmq_service
        )  # bind route_func
        await exitstack.enter_async_context(rmq_service)

        # Third, register rpc server
        server = grpc_aio_server(
            options=[
                ("grpc.keepalive_time_ms", 20000),
                ("grpc.keepalive_timeout_ms", 10000),
                ("grpc.http2.min_ping_interval_without_data_ms", 5000),
                # ("grpc.max_connection_idle_ms", 10000),
                # ("grpc.max_connection_age_ms", 30000),
                # ("grpc.max_connection_age_grace_ms", 5000),
                ("grpc.http2.max_pings_without_data", 5),
                ("grpc.keepalive_permit_without_calls", 1),
            ],
            maximum_concurrent_rpcs=1024,
        )
        add_UpstreamTransferServicer_to_server(servicer, server)

        server.add_insecure_port(proc.proc_manager.bind_addr)
        logger.info("Begin to start grpc server...")
        await server.start()
        logger.info("Server is listening...")

        def handle_exit(sig: int, frame: Optional[FrameType]):
            nonlocal closed
            if not closed:
                logger.info("Begin to shutdown server")
                closed = True
                get_running_loop().create_task(server.stop(5))

        install_signal_handlers(handle_exit)

        closed = False
        await server.wait_for_termination()
        logger.info("Server has shutdown")
