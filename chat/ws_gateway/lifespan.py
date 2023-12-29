from os import getpid
from logging import getLogger
from functools import partial
from typing import Optional, NamedTuple
from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack, asynccontextmanager

from asyncio import get_running_loop, BaseEventLoop
from starlette.types import ASGIApp

from chatp.utils.types import UID
from chatp.multiprocess.worker import WorkerProcess
from chatp.multiprocess.process import ProcessManager
from chatp.manager.grpc_client import GrpcClientManager


logger = getLogger("ASGIApp")
logger.setLevel(10)


@asynccontextmanager
async def monitor_wrapper(port: int, loop: BaseEventLoop = None):
    from aiomonitor import start_monitor

    if loop is None:
        loop = get_running_loop()

    with start_monitor(loop, port=port) as monitor:
        try:
            yield monitor
        except BaseException as exc:
            logger.info("ready to start clear monitor")


class ConsoleUserInfo(NamedTuple):
    uid: int


class LifeSpan:
    def __init__(
        self,
        proc: WorkerProcess,
        grpc_manager: GrpcClientManager,
        app_setting: Optional[dict],
    ):
        self.proc = proc
        self.grpc_manager = grpc_manager
        self.app_setting = app_setting

    def __call__(self, app: ASGIApp):
        return async_starter(self)


@asynccontextmanager
async def async_starter(lifespan: LifeSpan):
    pid = getpid()
    logger.info(f"enter ASGIApp's lifespan [{pid}]")

    loop = get_running_loop()
    loop.set_debug(True)
    executor = ThreadPoolExecutor(max_workers=4)
    loop.set_default_executor(executor)

    # must import these to trigger __init_subclass__
    # register local included_services
    from rpc.auth_service import AuthService
    from rpc.push_service import PushService
    from rpc.transfer_service import UpstreamTransferService
    from manager.session import SessionManager
    from manager.tasks import TaskManager
    from manager.push import PushManager

    # from rmq.service import RMQService # impl async push later
    from chatp.redis.client import RedisClient
    from chatp.rpc.grpc_service import GrpcService

    async with AsyncExitStack() as exitstack:  # LIFO
        setting = lifespan.app_setting

        proc = lifespan.proc
        grpc_manager = lifespan.grpc_manager

        proc_manager: ProcessManager = proc.proc_manager
        subscribe_key = f"{proc_manager.bind_addr}:{proc.process_seq}"
        SessionManager.bind(
            proc,
            platform_id=proc_manager.platform_id,
            gateway_addr=subscribe_key,
            appid_prefix=setting["APPID_PREFIX"],
        )

        task_manager = TaskManager()
        redis_client = RedisClient()
        session_manager = SessionManager()

        # binding service_consumer must be prior to `grpc_manager.__aenter__`
        push_manager = PushManager(
            grpc_manager=grpc_manager,
            ws_manager=session_manager,
            task_manager=task_manager,
            subscribe_key=subscribe_key,  # TODO fix this in single process
            loop=loop,
        )
        PushService.service_consumer = push_manager.connect_push_channel
        session_manager.bind_queue(push_manager.channel_queue)
        session_manager.bind_service_getter(
            partial(grpc_manager.find_service, "UpstreamTransferService")
        )

        # rmq_service = RMQService(setting)
        # rmq_service.bind_queue(push_manager.message_queue)

        logger.info(f"begin to start some services [{pid}]")

        # legacy - used siomisc.Service before
        # TODO should guarantee each src successful
        # if failed, maybe retry?
        # unless it is really unreachable, then should shutdown
        # entrypoint: when __aenter__, call _start -> gather(*[srv.start()])
        # gather's arg `return_exception` default value is False, so exc will be raised
        # when one srv failed to start, in this way main coroutine failed, then canceled
        # other all tasks in asyncio.run

        # entrypoint = aiomisc.Entrypoint(*services, loop=loop)
        # await _exitstack.enter_async_context(entrypoint)

        # this order is important
        # 1.cancel user read/write, for the underlaying transport is already closed
        # 2.after user read is cancelled, route-view task needs to safely exit (required redis)
        # 3.there may still some UserAcks required to be sent to PushService, but now it's still
        # likely to lost some acks
        await exitstack.enter_async_context(redis_client)  # Redis Connection
        await exitstack.enter_async_context(grpc_manager)  # all services' channels
        await exitstack.enter_async_context(push_manager)  # ack_to_user & ack_to_rpc
        # await exitstack.enter_async_context(rmq_service)  # MQ: publish/confirm
        await exitstack.enter_async_context(task_manager)  # cancel user read/write

        state = {
            "proc": proc,
            "redis_client": redis_client,
            "ws_manager": session_manager,
            "grpc_manager": grpc_manager,
            "task_manager": task_manager,
            # "publish_to_rmq": rmq_service.publish_message,
        }

        # monitor hook
        if port := setting["monitor_child_port"]:
            # aiomonitor block - info cllection
            # -> this can be used to collect infomation for main process's statistic
            # -> but now just used to debug
            # -> 1.higher extense than direct-pipe  2.invasiveness to view function
            monitor = await exitstack.enter_async_context(
                monitor_wrapper(port + proc.process_seq)
            )
            console_locals = monitor.console_locals
            console_locals["users"] = []
            console_locals["proc"] = proc
            console_locals["data"]: dict[UID, ConsoleUserInfo] = {}
            console_locals["session_manager"] = session_manager
            console_locals["task_manager"] = task_manager
            console_locals["push_manager"] = push_manager

            console_locals["GrpcService"] = GrpcService
            console_locals["AuthService"] = AuthService
            console_locals["UpstreamTransferService"] = UpstreamTransferService
            # console_locals["UserService"] = UserService
            # console_locals["RedisService"] = RedisService

            state["console_locals"] = console_locals

        # TODO monitor these services here or in each srv it self?

        logger.info(f"services are active [{pid}]")
        try:
            yield state  # may throw CancelledError in
        finally:
            # design of uvicorn's shutdown:
            # 1.close server sock -> shield new connections
            # 2.close existing connections -> close transport (1012 or 500)
            # 3.wait protocol to end its life -> Proctocol.connection_lost
            # 4.lifespan.shutdown -> clear application state
            #
            # with this application's shutdown variable:
            # 1.distinguish server shutdown or user kicked_off
            # 2.shield some unnecessary routine after underlaying connection is lost
            session_manager.shutdown = True

    # proc.close_child_pipe()  # child read (not need anymore, closed in task)
    logger.info(f"ASGIApp's life span shutdowned [{pid}]")
