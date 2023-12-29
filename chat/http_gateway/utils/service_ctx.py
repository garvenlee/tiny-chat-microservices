from sys import exc_info as sys_exc_info
from logging import getLogger
from inspect import iscoroutinefunction
from contextlib import AsyncExitStack
from concurrent.futures import Executor

from asyncio import get_running_loop
from blacksheep.server.application import Application

from chatp.manager.grpc_client import GrpcClientManager
from chatp.redis.client import RedisClient

from rmq.service import RMQService

logger = getLogger("ServicesRegisrationContext")


class ServicesRegisrationContext:
    def __init__(
        self,
        grpc_manager: GrpcClientManager,
        rmq_service: RMQService,
        redis_client: RedisClient,
        executor: Executor,
    ):
        self.grpc_manager = grpc_manager
        self.rmq_service = rmq_service
        self.executor = executor
        self.redis_client = redis_client

        self._instances = []
        self._dispose_maps = {}

    def register_instance(self, instance, instance_type=None, dispose_cb=None):
        if instance_type is None:
            instance_type = type(instance)
        self._instances.append((instance, instance_type))

        if dispose_cb:
            self._dispose_maps[instance_type] = dispose_cb

    async def initialize(self, app: Application):
        loop = get_running_loop()
        loop.set_debug(True)
        loop.set_default_executor(self.executor)

        from rpc.user_service import UserService
        from rpc.auth_service import AuthService
        from rpc.snowflake_service import SnowflakeService
        from rpc.cass_storage_service import CassMessageService
        from rpc.transfer_service import DownstreamTransferService

        grpc_manager = self.grpc_manager
        rmq_service = self.rmq_service
        redis_client = self.redis_client

        logger.info("begin to start some services...")

        self._exitstack = exitstack = AsyncExitStack()
        await exitstack.__aenter__()
        try:
            await exitstack.enter_async_context(grpc_manager)
            await exitstack.enter_async_context(rmq_service)
            await exitstack.enter_async_context(redis_client)
            logger.info("\tservices are active")
        except BaseException as exc:
            await exitstack.__aexit__(exc.__class__, exc, exc.__traceback__)
            raise
        else:
            # dependency declare
            container = app.services
            container.add_instance(grpc_manager)
            container.add_instance(rmq_service)
            container.add_instance(redis_client)
            for instance, instance_type in self._instances:
                container.add_instance(instance, instance_type)

    async def dispose(self, app: Application):
        logger.info("ready to exit ASGIApp's lifespan")
        # ps: the order is important
        # 1.Firstly, closed BackgroundTaskManager
        service_provider = app.service_provider
        for instance_type, dispose_func in self._dispose_maps.items():
            try:
                if iscoroutinefunction(dispose_func):
                    await dispose_func(service_provider[instance_type])
                else:
                    dispose_func(service_provider[instance_type])
            except BaseException as exc:
                logger.warning(f"Found exc when called {dispose_func.__name__}: {exc}")

        # 2.Secondly, closed GrpcClientManager & RMQService
        exc_tp, exc_val, exc_tb = sys_exc_info()
        await self._exitstack.__aexit__(exc_tp, exc_val, exc_tb)  # check later
        self._exitstack = None
        logger.info("\tASGIApp's life span has shutdown")
