from logging import getLogger
from typing import Optional
from asyncio import BaseEventLoop, get_running_loop

from cassandra.cluster import (
    Cluster,
    ExecutionProfile,
    NoHostAvailable,
    EXEC_PROFILE_DEFAULT,
)
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import (
    DCAwareRoundRobinPolicy,
    WhiteListRoundRobinPolicy,
    DowngradingConsistencyRetryPolicy,
    # RetryPolicy
)
from cassandra.query import (
    dict_factory,
    ordered_dict_factory,
    named_tuple_factory,
    ConsistencyLevel,
)

from chatp.database.exceptions import DriverError, InterfaceError
from chatp.database.builder import schema_builder
from ..base import AsyncBackendBase
from ..connection import AsyncioConnection
from ..session.cassandra import AsyncCassandraSession


logger = getLogger("AsyncCassandraBackend")


class AsyncCassandraBackend(AsyncBackendBase):
    DEFAULT_TIMEOUT: int = 30

    __slots__ = "_loop", "_initialized", "_keyspace", "cluster", "session"

    def __init__(
        self, *, conn_params: dict, loop: Optional[BaseEventLoop] = None, **kwargs
    ):
        if loop is None:
            loop = get_running_loop()
        self._loop = loop

        self._initialized = False
        self._keyspace = conn_params.get("keyspace")

        # firstly, bind the main eventloop
        AsyncioConnection.before_initialize_reactor(loop)
        # cluster will internally create a ThreadPoolExecutor
        self.cluster = self.build_cluster(conn_params, kwargs)
        self.session: Optional[AsyncCassandraSession] = None

    @classmethod
    def build_cluster(cls, conn_params: dict, extra_info: dict):
        hosts: list[str] = conn_params.get("host", ["127.0.0.1"])
        assert isinstance(hosts, list), "`host` in `conn_params` must be a list[str]."

        username, password = conn_params.get("username"), conn_params.get("password")
        if username is None or password is None:
            raise InterfaceError(
                "Key-Value missing in `conn_params`: `username` and `password`."
            )

        params = {
            "contact_points": hosts,
            "port": conn_params.get("port", 9042),
            "compression": True,
            "auth_provider": PlainTextAuthProvider(username, password),
            "connection_class": AsyncioConnection,
            "protocol_version": 4,
            "connect_timeout": 10,
            "idle_heartbeat_interval": 10,  # cassandra-driver's implementation is weird
            "idle_heartbeat_timeout": 10,
            "ssl_options": {},
            "executor_threads": extra_info.get("executor_threads", 5),
            "application_name": "Python cassandra-driver",
        }

        if (whitelist := extra_info.get("whitelist")) is not None:
            policy = WhiteListRoundRobinPolicy(whitelist)
        else:
            policy = DCAwareRoundRobinPolicy()
        timeout = extra_info.get("timeout", cls.DEFAULT_TIMEOUT)

        defaultprofile = ExecutionProfile(
            load_balancing_policy=policy,
            retry_policy=DowngradingConsistencyRetryPolicy(),
            request_timeout=timeout,
            row_factory=dict_factory,
            consistency_level=ConsistencyLevel.LOCAL_QUORUM,
            serial_consistency_level=ConsistencyLevel.LOCAL_SERIAL,
        )
        tupleprofile = ExecutionProfile(
            load_balancing_policy=policy,
            retry_policy=DowngradingConsistencyRetryPolicy(),
            request_timeout=timeout,
            row_factory=named_tuple_factory,
            consistency_level=ConsistencyLevel.LOCAL_QUORUM,
            serial_consistency_level=ConsistencyLevel.LOCAL_SERIAL,
        )
        orderedprofile = ExecutionProfile(
            load_balancing_policy=policy,
            retry_policy=DowngradingConsistencyRetryPolicy(),
            request_timeout=timeout,
            row_factory=ordered_dict_factory,
            consistency_level=ConsistencyLevel.LOCAL_QUORUM,
            serial_consistency_level=ConsistencyLevel.LOCAL_SERIAL,
        )

        return Cluster(
            execution_profiles={
                EXEC_PROFILE_DEFAULT: defaultprofile,
                "ordered": orderedprofile,
                "default": tupleprofile,
            },
            **params,
        )

    async def create_table(self, schema_dir: str) -> None:
        if not self._initialized:
            raise RuntimeError("sorry, still not connected to cassandra")

        session = self.session
        for _, schema in schema_builder(f"{schema_dir}/*.cql"):
            result = await session.query(schema)

    async def initialize(self):
        if self._initialized:
            return

        loop = self._loop
        cluster = self.cluster
        try:
            session = await loop.run_in_executor(
                cluster.executor, cluster.connect, self._keyspace
            )
        except NoHostAvailable as exc:
            raise DriverError(
                f"Not able to connect to any of the Cassandra contact points: {exc}"
            ) from exc
        except Exception as exc:
            logger.exception(f"Terminated: {exc}")
            raise ConnectionError(f"Terminated: {exc}")
        else:
            self.session = AsyncCassandraSession(session, loop)
            self._initialized = True
        return self.session

    async def close(self, timeout: int = 10):
        if (session := self.session) is not None:
            try:
                await session.close(timeout)
            finally:
                self.session = None
                cluster, self.cluster = self.cluster, None
                # internally closed its ThreadExecutorPool
                cluster.shutdown()
                self._initialized = False
