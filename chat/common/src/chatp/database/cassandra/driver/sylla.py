from logging import getLogger
from typing import Optional
from acsylla.base import ProtocolVersion as SyllaProtocolVersion
from acsylla.factories import create_cluster as create_sylla_cluster

from chatp.database.exceptions import InterfaceError
from chatp.database.builder import schema_builder
from ..base import AsyncBackendBase
from ..session.sylla import AsyncSyllaSession


logger = getLogger("AsyncSyllaBackend")


class AsyncSyllaBackend(AsyncBackendBase):
    __slots__ = "_initialized", "_keyspace", "cluster", "session"

    def __init__(self, *, conn_params: dict, **kwargs):
        """
        conn_params:
            host: str | list[str]
            port: int
            username: str
            password: str

        usable kwargs:
            connect_timeout
            request_timeout
            resolve_timeout
            num_threads_io
            consistency
        """

        if "username" not in conn_params or "password" not in conn_params:
            raise InterfaceError(
                "Key-Value missing in `conn_params`: `username` and `password`."
            )

        hosts: str | list[str] = conn_params.get("host", "127.0.0.1")
        port: int = conn_params.get("port", 9042)
        username: str = conn_params["username"]
        password: str = conn_params["password"]

        self.cluster = create_sylla_cluster(
            hosts,
            port,
            username=username,
            password=password,
            protocol_version=SyllaProtocolVersion.V4,
            num_threads_io=5,
            heartbeat_interval_sec=10,
            core_connections_per_host=8,
            application_name="Python acsylla",
            **kwargs,
        )
        self.session: Optional[AsyncSyllaSession] = None

        self._keyspace = conn_params.get("keyspace")
        self._initialized = False

    async def create_table(self, schema_dir: str) -> None:
        if not self._initialized:
            raise RuntimeError("sorry, still not connected to cassandra")

        session = self.session
        for _, schema in schema_builder(f"{schema_dir}/*.cql"):
            result = await session.query(schema)

    async def initialize(self):
        if self._initialized:
            return

        try:
            session = await self.cluster.create_session(self._keyspace)
        except Exception as exc:
            logger.exception(f"Terminated: {exc}")
            raise ConnectionError(f"Terminated: {exc}")
        else:
            self._initialized = True

            self.session = sylla_session = AsyncSyllaSession(session)
            return sylla_session

    async def close(self, timeout: int = 10):
        if (session := self.session) is not None:
            try:
                await session.close(timeout)
            finally:
                self.session = None
                self.cluster = None
                self._initialized = False
