from random import random
from types import FrameType
from typing import Optional

from asyncio import get_running_loop, sleep
from grpc.aio import server as grpc_aio_server
from opentelemetry.instrumentation.grpc import aio_server_interceptor

from chatp.manager.grpc_client import GrpcClientManager
from chatp.multiprocess.process import ProcessManager
from chatp.multiprocess.worker import WorkerProcess
from chatp.starter import AsyncMultiProcessManager
from chatp.utils.signals import install_signal_handlers

from snowflake import SnowflakeGenerator
from snowflake_service import SnowflakeServicer, logger
from chatp.proto.services.snowflake.snowflake_pb2_grpc import (
    add_SnowflakeServicer_to_server,
)


async def wait_for_instance_id(proc_manager: ProcessManager):
    shared_array = proc_manager.shared_array
    while not (data := shared_array[0]):
        await sleep(0)

    with shared_array.get_lock():
        data = shared_array[0]
        ripple = (data & 0xF0) >> 4
        instance_id = shared_array[ripple]
        if data & 0x0F > 1:
            shared_array[0] -= 1
        else:
            shared_array[0] = 0
            shared_array[ripple] = 0

    return instance_id


async def serve(
    proc: WorkerProcess, grpc_manager: GrpcClientManager, app_setting: Optional[dict]
) -> None:
    del grpc_manager  # TODO at least write load, but currently dont impl

    instance_id = await wait_for_instance_id(proc.proc_manager)
    instance_id += proc.process_seq - 1

    server = grpc_aio_server(
        interceptors=[aio_server_interceptor()],
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
        maximum_concurrent_rpcs=4096,
    )
    add_SnowflakeServicer_to_server(
        SnowflakeServicer(
            SnowflakeGenerator(instance_id, epoch=app_setting["CHATAPP_EPOCH"])
        ),
        server,
    )

    del app_setting
    server.add_insecure_port(proc.proc_manager.bind_addr)
    logger.warning("begin to start grpc server...")
    await server.start()
    logger.warning("grpc server is listening")

    def handle_exit(sig: int, frame: Optional[FrameType]):
        nonlocal closed
        if not closed:
            logger.info("begin to shutdown server")
            get_running_loop().create_task(server.stop(5))

    install_signal_handlers(handle_exit)

    closed = False
    await server.wait_for_termination()
    logger.warning("server has shutdown")


# Option: Redis Lock & incr - it's simple, but still needs to save something in etcd
# -> ETCD Lock & Redis incr, lock is safer and more stable.
async def get_or_flick_instance_id(manager: AsyncMultiProcessManager):
    from redis.asyncio import Redis
    from redis.asyncio.retry import Retry
    from redis.backoff import EqualJitterBackoff
    from redis.exceptions import ConnectionError, BusyLoadingError

    setting = manager.app_setting
    ETCD_INSTANCE_ID_PREFIX = setting["ETCD_INSTANCE_ID_PREFIX"]
    ETCD_INSTANCE_ID_LOCK = setting["ETCD_INSTANCE_ID_LOCK"]
    REDIS_INSTANCE_ID_KEY = setting["REDIS_INSTANCE_ID_KEY"]

    service_manager = manager.service_manager
    client = service_manager.client
    platform_key = bytes(
        f"{ETCD_INSTANCE_ID_PREFIX}{service_manager.platform_id}", "ascii"
    )

    num_workers = manager.process_manager.num_workers
    resp = await client.get(platform_key)
    if resp is not None:
        data = resp.value.decode("ascii").split(",")
        start_id, length = int(data[0]), int(data[1])
        if length < num_workers:
            # TODO Flexible Id Dispatcher
            raise RuntimeError(
                f"configure too many workers, currenly allowed maximum {length}"
            )
        return start_id

    etcd_lock = client.lock(bytes(ETCD_INSTANCE_ID_LOCK, "ascii"), ttl=30)
    redis_incr_key = REDIS_INSTANCE_ID_KEY
    while True:
        success = await etcd_lock.acquire()
        if not success:
            await sleep(0.2 + random())
            continue

        try:
            async with Redis(
                single_connection_client=True,
                socket_timeout=1,  # used in `read_response`
                socket_connect_timeout=3,  # used in `connect`
                # retry_on_timeout=True,
                retry=Retry(
                    EqualJitterBackoff(base=0.02),  # 20ms
                    3,
                    supported_errors=(ConnectionError, BusyLoadingError),
                ),
            ) as redis:
                end_id: int = await redis.incr(redis_incr_key, amount=num_workers)
        except BaseException:
            await sleep(0.5 + random())
            continue
        else:
            start_id = end_id - num_workers + 1
            await client.put(platform_key, bytes(f"{start_id},{num_workers}", "ascii"))
            return start_id
        finally:
            await etcd_lock.release()  # if failed, wait ttl?
