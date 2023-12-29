from logging import getLogger
from enum import IntEnum
from time import monotonic
from itertools import repeat
from collections import deque
from contextlib import asynccontextmanager

from typing import Optional, Sequence, Any, cast

from asyncio import (
    sleep,
    wait,
    wait_for,
    create_task,
    Future,
    CancelledError,
    TimeoutError as AsyncIOTimeoutError,
)
from aiomisc import CircuitBroken
from asyncpg.pool import Pool, PoolConnectionProxy, create_pool
from asyncpg.connection import Connection as AsyncpgConnection
from asyncpg.prepared_stmt import PreparedStatement
from asyncpg.exceptions import (
    UniqueViolationError,
    ConnectionDoesNotExistError,
    # QueryCanceledError,
    # InterfaceError,
    # InternalClientError,
)

from ..builder import schema_builder
from ..model import *
from chatp.utils.circuit_breaker import CircuitBreakerMixin

logger = getLogger("PostgresBackend")
logger.setLevel(10)


class AsyncMyBackend:
    """
    Responsible for being the interface between the DB and the application
    """

    HOST: str = "127.0.0.1"
    PORT: int = 5432

    USER: str = "root"
    DEFAULT_DB: str = "chatApp"

    POOL_MAX_SIZE: int = 10
    POOL_MIN_SIZE: int = 4
    POOL_RESERVE_SIZE: int = 5

    CONNECT_TIMEOUT: int = 3
    COMMAND_TIMEOUT: int = 10

    STATEMENT_CACHE_SIZE = 100  # 100 entry at most
    MAX_CACHED_STATEMENT_LIFETIME = 0  # dont expired
    MAX_CACHEABLE_STATEMENT_SIZE = 1024 * 15  # one entry reaches 15kib at most

    def __init__(
        self,
        host: str,
        port: int,  # mysql 3306 postgres 5432
        user: str,
        password: str,
        db: str,
        **kwargs,
    ) -> None:
        if password is None:
            raise Exception("PostgresSQL password must be given.")
        self.password = password

        self_cls = self.__class__
        self.host = host or self_cls.HOST
        self.port = port or self_cls.PORT
        self.user = user or self_cls.USER
        self.db = db or self_cls.DEFAULT_DB

        # TODO TYPE CHECK
        kwargs_pop = kwargs.pop
        self.max_size = kwargs_pop("max_size", self_cls.POOL_MAX_SIZE)
        self.min_size = kwargs_pop("min_size", self_cls.POOL_MIN_SIZE)
        # reserve for transaction
        self._reserve_size = self_cls.POOL_RESERVE_SIZE

        self.on_setup = kwargs_pop("setup", None)  # called in `acquire`
        self.on_init = kwargs_pop("init", None)  # called in `get_new_connection`
        self._connect_timeout = kwargs_pop(
            "connection_timeout", self_cls.CONNECT_TIMEOUT
        )
        self._command_timeout = kwargs_pop("command_timeout", self_cls.COMMAND_TIMEOUT)
        self._statement_cache_size = kwargs_pop(
            "statement_cache_size", self_cls.STATEMENT_CACHE_SIZE
        )
        self._max_cached_statement_lifetime = kwargs_pop(
            "max_cached_statement_lifetime", self_cls.MAX_CACHED_STATEMENT_LIFETIME
        )
        self._max_cacheable_statement_size = kwargs_pop(
            "max_cacheable_statement_size", self_cls.MAX_CACHEABLE_STATEMENT_SIZE
        )

        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        # another design: execute `on_init` when conn_pool spawns a new connection
        #   - prepare the query_cache
        #   - this produces several network op, which may lead to response jitter
        #   - so just postpone the preparation to the actual execution of the stmt
        self._conn_pool: Pool = await create_pool(
            max_size=self.max_size + self._reserve_size,
            min_size=self.min_size,
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.db,
            setup=self.on_setup,  # Callable[[ConnectionProxy], Coroutine]
            init=self.on_init,  # Callable[[Connection], Coroutine]
            timeout=self._connect_timeout,
            command_timeout=self._command_timeout,
            statement_cache_size=self._statement_cache_size,
            max_cached_statement_lifetime=self._max_cached_statement_lifetime,
            max_cacheable_statement_size=self._max_cacheable_statement_size,
        )
        self._initialized = True

    async def create_table(self, schema_dir: str) -> None:
        async with self._conn_pool.acquire() as conn:
            conn = cast(AsyncpgConnection, conn)  # in fact, conn is a ConnProxy
            conn_execute = conn.execute
            for _, schema in schema_builder(f"{schema_dir}/*.sql"):
                await conn_execute(schema)

    async def close(self):
        pool, self._conn_pool = self._conn_pool, None
        try:
            await wait_for(pool.close(), timeout=10)
        except AsyncIOTimeoutError:
            pass

    def connection(self) -> "AsyncMyConnection":
        return AsyncMyConnection(self._conn_pool)

    def transaction(
        self,
        isolation: str = "read_commited",
        readonly: bool = False,
        deferrable: bool = False,
    ) -> "AsyncMyTransaction":
        return AsyncMyTransaction(self, isolation, readonly, deferrable)


# TODO this design adds twice attribute find
class AsyncMyConnection:
    __slots__ = (
        "_pool_acquire",
        "_pool_release",
        "_connection",
        "_stmt_cache",
        "last_usage",
    )

    def __init__(self, pool: Pool) -> None:
        self._pool_acquire = pool._acquire
        self._pool_release = pool.release
        self._connection: Optional[PoolConnectionProxy] = None
        self._stmt_cache: dict[str, PreparedStatement] = {}  # query : PreparedStatement

    @property
    def in_use(self):
        return self._connection is not None

    def transaction(
        self,
        isolation: str = "read_committed",
        readonly: bool = False,
        deferrable: bool = False,
    ) -> "AsyncMyTransaction":
        connection: AsyncpgConnection = self._connection
        return connection.transaction(
            isolation=isolation, readonly=readonly, deferrable=deferrable
        )

    async def bind(self, timeout: float) -> bool:
        if self._connection is None:
            try:
                # connect_timeout default 3 when create pool
                self._connection = await self._pool_acquire(timeout)
            except (
                OSError,
                ConnectionError,
                AsyncIOTimeoutError,
                CancelledError,
            ) as exc:
                logger.error(
                    f"[AsyncMyConnection] Found excption in `bind`: {exc.__class__} / {exc}"
                )
                # await self.detach()
                raise
            except BaseException as exc:
                logger.error(
                    f"[AsyncMyConnection] Found excption in `bind`: {exc.__class__} / {exc}"
                )
                # await self.detach()
                return False
            else:
                self.last_usage = monotonic()
                return True
        return False

    async def detach(self):
        if (conn := self._connection) is not None:
            # stmt_cache, self._stmt_cache = self._stmt_cache, None
            # del stmt_cache  # trigger stmt clear

            self._connection = None
            try:
                await self._pool_release(conn)
            except CancelledError:  # failed to reset
                pass
            except (
                BaseException
            ) as exc:  # the next accquire will create a new connection
                logger.error(
                    f"[AsyncMyConnection] Found excption in `detach`: {exc.__class__} / {exc}"
                )

            self.last_usage = monotonic()

    # TODO CHECK: connection is still in use when closing corresponding task
    async def wait_for_terminate(self, timeout: int = 5):
        await sleep(timeout)
        if (conn := self._connection) is not None:  # TODO check exc
            self._connection = None
            await self._pool_release(conn)

    async def batch_write(
        self,
        sql: str,
        values: Sequence[tuple[str]],
        *,
        timeout: int = 8,
    ) -> ExecutionResult:
        conn: AsyncpgConnection = self._connection
        try:
            # executemant just return None if succeed else raise exc
            await conn.executemany(sql, values, timeout=timeout)  # autocommit
        except ConnectionDoesNotExistError as exc:
            # connection was closed in the middle of operation
            result = ExecutionResult(DB_PANIC_IO_ERROR, exc.args[0])
        except AsyncIOTimeoutError as exc:
            msg = "Timeout in asyncpg when insert"
            logger.info(msg)
            result = ExecutionResult(DB_TIMEOUT_HANDLING, msg)
        except BaseException as exc:  # TODO exc check
            logger.exception(exc)
            result = ExecutionResult(DB_FAILED, str(exc))
        else:
            msg = f"executemany succeed: batch {len(values)}\nexecuted:{sql}\n"
            logger.info(msg)
            result = ExecutionResult(DB_SUCCESS, msg)

        return result

    async def create(
        self,
        sql: str,
        values: tuple[str],
        *,
        returning: bool = False,
        timeout: int = 8,
    ) -> ExecutionResult:
        try:
            if (stmt := self._stmt_cache.get(sql)) is not None:
                if returning:
                    data = await stmt.fetchrow(*values, timeout=timeout)  # autocommit
                else:
                    _ = await stmt.fetch(*values, timeout=timeout)
                    data = stmt.get_statusmsg()
            else:
                connection: AsyncpgConnection = self._connection
                meth = connection.fetchrow if returning else connection.execute
                data = await meth(sql, *values, timeout=timeout)
        except UniqueViolationError as exc:  # key conflict
            msg = exc.args[0]
            logger.exception(msg)
            result = ExecutionResult(DB_INFO_DUP_ENTRY, msg)
        except ConnectionDoesNotExistError as exc:
            # connection was closed in the middle of operation
            msg = exc.args[0]
            logger.error(msg)
            result = ExecutionResult(DB_PANIC_IO_ERROR, msg)
        except AsyncIOTimeoutError as exc:
            msg = "Timeout in asyncpg when insert"
            logger.info(msg)
            result = ExecutionResult(DB_TIMEOUT_HANDLING, msg)
        except Exception as exc:  # TODO exc check
            # InterfaceError -> broken connection
            # InternalClientError
            logger.exception(exc)
            msg = str(exc)
            result = ExecutionResult(DB_FAILED, msg)
        else:
            msg = f"create succeed: {sql}"
            logger.info(msg)
            # INSERT 0 1 if succeed
            result = ExecutionResult(DB_SUCCESS, msg, data=data)

        return result

    async def read(
        self,
        sql: str,
        values: tuple[str],
        *,
        all: bool = False,
        timeout: int = 3,
    ) -> ExecutionResult:
        conn: AsyncpgConnection = self._connection
        try:
            if all:  # all records -> [] or [Records]
                records = await conn.fetch(sql, *values, timeout=timeout)
                msg = f"read fetchall, totally {len(records)}"
            else:  # just the first row
                records = await conn.fetchrow(sql, *values, timeout=timeout)
                msg = f"read fetchone: {records}"
        except ConnectionDoesNotExistError as exc:
            msg = exc.args[0]
            logger.error(msg)
            result = ExecutionResult(DB_PANIC_IO_ERROR, msg)
        except AsyncIOTimeoutError as exc:
            msg = f"Timeout in asyncpg when read : {sql}"
            logger.info(msg)
            result = ExecutionResult(DB_TIMEOUT_HANDLING, msg)
        except Exception as exc:
            logger.exception(exc)
            result = ExecutionResult(DB_FAILED, str(exc))
        else:
            logger.info(msg)
            result = ExecutionResult(DB_SUCCESS, msg, records)
        return result

    async def update(
        self,
        sql: str,
        values: tuple[str],
        *,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        conn: AsyncpgConnection = self._connection

        try:
            data = await conn.execute(sql, *values, timeout=timeout)
        except ConnectionDoesNotExistError as exc:
            msg = exc.args[0]
            logger.error(msg)
            # connection was closed in the middle of operation
            result = ExecutionResult(DB_PANIC_IO_ERROR, msg)
        except AsyncIOTimeoutError as exc:
            msg = f"Timeout in asyncpg when update: {sql}"
            logger.info(msg)
            result = ExecutionResult(DB_TIMEOUT_HANDLING, msg)
        except Exception as exc:  # TODO exc check
            logger.exception(exc)
            result = ExecutionResult(DB_FAILED, str(exc))
        else:
            msg = f"update succeed: {sql}"
            logger.info(msg)
            # UPDATE 0 or UPDATE 1
            result = ExecutionResult(DB_SUCCESS, msg, data=data)

        return result


class AsyncMyTransaction:
    pass


class AsyncMyConnectionPoolState(IntEnum):
    ACTIVE = 0
    CLOSING = 1
    CLOSED = 2


class AsyncMyConnectionPool(CircuitBreakerMixin):
    __slots__ = (
        "backend",
        "state",
        "_used",
        "_free",
        "_waiters",
        "_stmt_cache",
        "_initialized",
    )

    exceptions = (OSError, ConnectionError, AsyncIOTimeoutError, CancelledError)

    # TODO check time config
    ERROR_RATIO: float = 0.2
    RESPONSE_TIME: int = 10
    PASSING_TIME: int = 2
    BROKEN_TIME: int = 5
    RECOVERY_TIME: int = 3

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5432,  # mysql 3306 postgres 5432
        user: str = "garvenlee",
        password: Optional[str] = None,
        db: str = "chatApp",
        max_size: int = 10,
        min_size: int = 10,
        **kwargs,
    ) -> None:
        conn_kwargs = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "db": db,
            "max_size": max_size,
            "min_size": min_size,
        }
        self.backend = AsyncMyBackend(**conn_kwargs, **kwargs)
        self.state = AsyncMyConnectionPoolState.ACTIVE

        self._used: set[AsyncMyConnection] = set()
        self._free: deque[AsyncMyConnection] = deque()
        self._waiters: deque[Future] = deque()

        self._stmt_cache: dict[str, Any] = {}

        self._initialized = False

    @property
    def capacity(self):
        return self.backend.max_size

    async def initialize(self):
        if self._initialized:
            return

        await self.backend.initialize()  # if needs

        free_append = self._free.append
        connection_builder = self.backend.connection
        for _ in repeat(None, self.capacity):
            free_append(connection_builder())

        self.cb_initialize()
        # self._monitor_task = create_task(self.monitor())
        self._initialized = True

    async def acquire(self, timeout: float = 5) -> Optional[AsyncMyConnection]:
        if self.state is AsyncMyConnectionPoolState.ACTIVE:
            usable, used = self._free, self._used
            if usable:
                conn = usable.popleft()
                # connection maybe refused or timeout or cancelled
                try:
                    with self._circuit_breaker.context():
                        if not await conn.bind(timeout):
                            usable.append(conn)  # BaseException ?
                            return
                except CircuitBroken as exc:
                    logger.error(
                        f"[AsyncConnectionPool] Found Broken in `acquire`: {exc.__class__} / {exc}"
                    )
                    usable.append(conn)
                    return
                except BaseException as exc:
                    logger.error(
                        f"[AsyncConnectionPool] Found exc in `acquire`: {exc.__class__} / {exc}"
                    )
                    usable.append(conn)
                    return
            else:
                fut = Future()
                waiters = self._waiters
                waiters.append(fut)
                try:
                    conn = await wait_for(fut, timeout=timeout)
                except (
                    AsyncIOTimeoutError,  # timeout
                    CancelledError,  # closed when Grpc-task wait for db conn or cancelled by the peer
                ):
                    # waiters.remove(fut)  # O(n)
                    return
                except BaseException as exc:
                    logger.error(
                        f"[AsyncConnectionPool] Found exception in `acquire`<waiter>: {exc.__class__} / {exc}"
                    )
                    return

            used.add(conn)
            return conn

    async def release(self, conn: AsyncMyConnection) -> None:
        if waiters := self._waiters:
            waiters_popleft = waiters.popleft
            try:
                while (waiter := waiters_popleft()).done():
                    continue
            except IndexError:
                await conn.detach()
                self._used.discard(conn)
                self._free.append(conn)
            else:
                # just reuse it, dont release this conn to the pool
                # but needs to check it's max_queries
                waiter.set_result(conn)
        else:
            await conn.detach()
            self._used.discard(conn)
            self._free.append(conn)

    @asynccontextmanager
    async def connection(self):
        try:
            conn = await self.acquire()
            yield conn
        finally:
            if conn is not None:
                await self.release(conn)

    async def close(self):
        self.state = AsyncMyConnectionPoolState.CLOSING

        self._free = None
        if used := self._used:
            self._used = None
            wait_tasks = [
                create_task(conn.wait_for_terminate()) for conn in used if conn.in_use
            ]
            if wait_tasks:
                await wait(wait_tasks)  # TODO check, maybe exc

        waiters: deque[Future] = self._waiters
        self._waiters = None
        if waiters:
            for waiter in waiters:
                if not waiter.done():
                    waiter.set_exception(CancelledError("service shutdown"))
            await sleep(0)  # wait waiters to complete

        backend, self.backend = self.backend, None
        await backend.close()

        self.state = AsyncMyConnectionPoolState.CLOSED
