from logging import getLogger
from types import FrameType
from typing import Optional
from contextlib import AsyncExitStack
from asyncio import get_running_loop

from chatp.multiprocess.worker import WorkerProcess
from chatp.redis.client import RedisClient
from chatp.manager.grpc_client import GrpcClientManager
from chatp.utils.signals import install_signal_handlers


logger = getLogger("TransferService")
logger.setLevel(10)


async def serve(
    proc: WorkerProcess, grpc_manager: GrpcClientManager, app_setting: Optional[dict]
):
    from grpc.aio import server as grpc_aio_server
    from chatp.proto.services.transfer.downstream_pb2_grpc import (
        add_DownstreamTransferServicer_to_server,
    )

    from rmq.service import RMQService
    from downstream_service import DownstreamTransferServicer

    logger.info("begin to start db_service...")
    async with AsyncExitStack() as exitstack:
        # First, initialize grpc client
        redis_client = RedisClient()
        await exitstack.enter_async_context(redis_client)
        await exitstack.enter_async_context(grpc_manager)

        # Second, initialize rmq_service
        app_setting["READ_MODEL_EVENT_QUEUE_NAME"] = (
            app_setting["READ_MODEL_EVENT_QUEUE_NAME_PREFIX"]
            + proc.proc_manager.platform_id
        )
        rmq_service = RMQService(app_setting)
        await exitstack.enter_async_context(rmq_service)
        create_task = get_running_loop().create_task

        broker_id = app_setting["APPID_PREFIX"] + "X" * 48
        servicer = DownstreamTransferServicer(
            grpc_manager, redis_client, rmq_service, broker_id
        )
        rmq_task = create_task(rmq_service.run(servicer.consume_event))

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
        add_DownstreamTransferServicer_to_server(servicer, server)
        server.add_insecure_port(proc.proc_manager.bind_addr)

        logger.info("begin to start grpc server...")
        await server.start()
        logger.info("grpc server is listening")

        def handle_exit(sig: int, frame: Optional[FrameType]):
            nonlocal closed
            logger.info("begin to shutdown server")
            if not closed:
                closed = True
                rmq_task.cancel()  # TODO Add DLQ for this queue
                rmq_task.add_done_callback(lambda _: create_task(server.stop(5)))

        closed = False
        install_signal_handlers(handle_exit)
        await server.wait_for_termination()
        logger.info("server has shutdown")
