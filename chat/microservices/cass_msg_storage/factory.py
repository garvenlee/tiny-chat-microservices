from typing import Optional
from types import FrameType
from chatp.multiprocess.worker import WorkerProcess
from chatp.manager.grpc_client import GrpcClientManager


async def serve(
    proc: WorkerProcess, grpc_manager: GrpcClientManager, app_setting: Optional[dict]
):
    from logging import getLogger
    from contextlib import AsyncExitStack
    from asyncio import get_running_loop
    from grpc.aio import server as grpc_aio_server

    from chatp.utils.signals import install_signal_handlers
    from chatp.redis.client import RedisClient
    from chatp.proto.services.transfer.cass_storage_pb2_grpc import (
        add_CassStorageServicer_to_server,
    )
    from db_service import DbService
    from cass_storage_service import CassStorageService

    del grpc_manager

    logger = getLogger("CassStorageService")
    logger.setLevel(10)
    redis_client = RedisClient()
    db_service = DbService(
        username=app_setting["CASS_USERNAME"],
        password=app_setting["CASS_PASSWORD"],
        host=app_setting["CASS_HOST"],
        port=app_setting["CASS_PORT"],
        keyspace=app_setting["CASS_KEYSPACE"],
        # request_timeout=32,  # default 12
    )

    async with AsyncExitStack() as exitstack:
        await exitstack.enter_async_context(db_service)
        await exitstack.enter_async_context(redis_client)

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
        cass_servicer = CassStorageService(db_service.executor, redis_client)
        add_CassStorageServicer_to_server(cass_servicer, server)

        server.add_insecure_port(proc.proc_manager.bind_addr)
        logger.info("Begin to start grpc server...")
        await server.start()
        logger.info("Server is listening...")

        def handle_exit(sig: int, frame: Optional[FrameType]):
            logger.info(f"> Catched signal {sig} from os kernel")
            nonlocal closed
            if not closed:
                closed = True
                cass_servicer.shutdown = True
                get_running_loop().create_task(server.stop(10))

        closed = False
        install_signal_handlers(handle_exit)
        await server.wait_for_termination()
        logger.info("Server has shutdown, begin to clear AsyncExitStack")
