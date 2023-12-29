from logging import getLogger
from typing import Optional, Union, Any
from functools import partial
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from anyio import fail_after
from asyncio import (
    BaseEventLoop,
    Event,
    wait,
    gather,
    get_running_loop,
    FIRST_COMPLETED,
)

from cassandra import ReadTimeout
from cassandra.cluster import (
    Session as CassandraSession,
    ResponseFuture,
    ResultSet,
    EXEC_PROFILE_DEFAULT,
)
from cassandra.query import (
    ConsistencyLevel,
    PreparedStatement as CassPreparedStatement,
    SimpleStatement as CassSimpleStatement,
    BatchStatement,
    BatchType,
)
from cassandra.metadata import protect_name

from chatp.database.exceptions import NoDataFound, DriverError
from chatp.database.model import CachedStatement
from ..base import AsyncSessionBase

logger = getLogger("AsyncCassandraSession")


cass_consistency_map = {"quorum": ConsistencyLevel.QUORUM, "all": ConsistencyLevel.ALL}


def create_cass_statement(sentence: str, *, consistency: str = "quorum"):
    cl = cass_consistency_map.get(consistency)
    if cl is None:
        raise RuntimeError(f"Unsupported consistency: {consistency}")
    return CassSimpleStatement(sentence, consistency_level=cl)


class Paginator:
    __slots__ = (
        "_loop",
        "_request",
        "_executor",
        "response_fut",
        "_deque",
        "_drain_event",
        "_finish_event",
        "_exit_event",
        "_exc",
        "__pages",
    )

    def __init__(self, request, *, executor: ThreadPoolExecutor, loop: BaseEventLoop):
        self._request = request
        self._executor = executor
        self._loop: BaseEventLoop = loop

        self._exc = None
        self.response_fut: Optional[ResponseFuture] = None

        self._drain_event = Event()
        self._finish_event = Event()
        self._exit_event = Event()

        self.__pages = set()
        self._deque = deque()

    def _handle_page(self, rows):
        if self._exit_event.is_set():
            logger.debug("Paginator is closed, skipping new %i records", len(rows))
            return

        self._deque.extend(rows)  # here maybe blocked.
        self._drain_event.set()

        if self.response_fut.has_more_pages:
            _fn = self.response_fut.start_fetching_next_page
            fut = self._loop.run_in_executor(self._executor, _fn)
            self.__pages.add(fut)
            fut.add_done_callback(self.__pages.discard)
            return

        self._finish_event.set()

    def _handle_err(self, exc):
        self._exc = exc
        self._finish_event.set()

    async def __aenter__(self):
        response_fut: ResponseFuture = await self._loop.run_in_executor(
            self._executor, self._request
        )
        response_fut.add_callbacks(callback=self._handle_page, errback=self._handle_err)
        self.response_fut = response_fut
        return self

    async def __aexit__(self, *exc_info):
        self._exit_event.set()
        _len = len(self._deque)
        self._deque.clear()
        logger.debug("Paginator is closed, cleared in-memory &i records", _len)

        await gather(*self.__pages)

    async def __aiter__(self):
        return self._paginator()

    async def _paginator(self):
        if self.response_fut is None:
            raise RuntimeError("Paginaton should be done inside asybc context manager")

        data_deque = self._deque
        drain_event = self._drain_event
        finish_event = self._finish_event
        while data_deque or not finish_event.is_set() or self._exc is not None:
            if self._exc is not None:
                raise self._exc

            while data_deque:
                yield data_deque.popleft()

            await wait(
                (drain_event.wait(), finish_event.wait()),
                return_when=FIRST_COMPLETED,
            )


class AsyncCassandraSession(AsyncSessionBase):
    TEST_QUERY = "SELECT release_version FROM system.local"
    RAW_QUERY = "SELECT {fields} FROM {table} {where_cond}"

    __slots__ = (
        "_loop",
        "_loop_run_in_executor",
        "_executor",
        "_cass_session",
        "_cass_execute_async",
        "_cached_statements",
        "_cached_prepared",
    )

    def __init__(
        self, session: CassandraSession, *, loop: Optional[BaseEventLoop] = None
    ):
        if loop is None:
            loop = get_running_loop()
        self._loop = loop

        self._cass_session = session
        self._cass_execute_async = session.execute_async

        executor = session.cluster.executor
        self._executor = executor
        self._loop_run_in_executor = partial(loop.run_in_executor, executor)

        self._cached_statements: dict[str, CassSimpleStatement] = dict()
        self._cached_prepared: dict[str, CachedStatement] = dict()

    # TODO must check there are still any inflight network IO
    async def close(self, timeout: int):
        try:
            with fail_after(timeout):
                await self._loop_run_in_executor(self._cass_session.shutdown)
        except Exception as exc:
            raise DriverError(f"Connection Error, Terminated: {exc}")
        finally:
            self._cass_session = None
            self._cass_execute_async = None
            self._loop_run_in_executor = None
            self._executor = None

    # check whether or not uses `run_in_executor`
    async def execute_future(self, *args, **kwargs):
        loop: BaseEventLoop = self._loop
        response: ResponseFuture = self._cass_execute_async(*args, **kwargs)
        # response: ResponseFuture = await loop.run_in_executor(
        #     self._executor, self._cass_execute_async, *args, **kwargs
        # )
        waiter = loop.create_future()
        response.add_callback(lambda res: waiter.set_result(ResultSet(response, res)))
        response.add_errback(lambda exc: waiter.set_exception(exc))
        return await waiter

    def execute_futures(self, *args, **kwargs):
        _request = partial(self._cass_execute_async, *args, **kwargs)
        return Paginator(_request, executor=self._executor, loop=self._loop)

    async def find(self, cql: str, *, bind_params: dict, **kwargs):
        item = await self.get_or_create_prepared(cql)
        prepared = item.prepared
        stmt = prepared.bind(**bind_params)
        return self.execute_futures(stmt, **kwargs)

    def get_or_create_statement(self, cql: str, *, consistency: str = "quorum"):
        cached_statements = self._cached_statements
        stmt = cached_statements.get(cql)
        if stmt is None:
            stmt = create_cass_statement(cql, consistency)
            cached_statements[cql] = stmt
        return stmt

    async def get_or_create_prepared(
        self,
        cql: str,
        *,
        consistency: str = "quorum",
        timeout: float = 5.0,
    ):
        cl = cass_consistency_map.get(consistency)
        if cl is None:
            raise RuntimeError(f"Unsupported consistency: {consistency}")

        cached_prepared = self._cached_prepared
        item = cached_prepared.get(cql)
        if prepared is None:
            try:
                prepared = await self._loop_run_in_executor(
                    self._cass_session.prepare, cql
                )
            except RuntimeError as exc:
                raise Exception(f"Runtime Error: {exc}") from exc
            except Exception as exc:
                raise Exception(f"Error on Query: {exc}") from exc
            else:
                prepared.consistency_level = cl
                item = CachedStatement(cql, prepared, prepared.bind())
                cached_prepared[cql] = item
        return item

    async def test_connection(self):  # pylint: disable=W0221
        result = error = None
        try:
            result = await self.execute_future(self.TEST_QUERY)
        except Exception as exc:  # pylint: disable=W0703
            error = exc
        finally:
            return result, error  # pylint: disable=W0150

    async def use(self, database: str):
        try:
            await self.execute_future("USE %s" % (protect_name(database),))
        except Exception as err:
            logger.exception(err)
            raise
        return self

    async def query(
        self,
        cql: str,
        factory: str = EXEC_PROFILE_DEFAULT,
        **kwargs,
    ) -> Union[ResultSet, None]:
        result = error = None
        stmt = self.get_or_create_statement(cql)

        try:
            result: ResultSet = await self.execute_future(
                stmt, execution_profile=factory, **kwargs
            )
            if result is None:
                raise NoDataFound("Cassandra: No Data was Found")
        except ReadTimeout:
            error = f"Timeout reading Data from {cql}"
        except NoDataFound:
            raise
        except RuntimeError as exc:
            error = f"Runtime Error: {exc}"
        except Exception as exc:  # pylint: disable=W0703
            error = f"Error on Query: {exc}"
        finally:
            return result, error

    async def fetch_all(
        self,
        cql: str,
        params: tuple,
        **kwargs,
    ) -> ResultSet:
        try:
            result = await self.execute_future(cql, params, **kwargs)
        except RuntimeError as exc:
            raise DriverError(f"Runtime Error: {exc}") from exc
        except Exception as exc:
            raise Exception(f"Error on Query: {exc}") from exc
        else:
            if result is None:
                raise NoDataFound("Cassandra: No Data was Found")
            return result

    async def fetch(self, sentence, params: Optional[list] = None):
        if params is None:
            params = []
        return await self.fetch_all(sentence, params)

    async def queryrow(
        self,
        cql: str,
        params: Optional[tuple] = None,
    ):
        result = error = None
        try:
            result = await self.execute_future(cql, params).one()
            if result is None:
                error = "Cassandra: No Data was Found"
        except RuntimeError as exc:
            error = f"Runtime on Query Row Error: {exc}"
        except Exception as exc:  # pylint: disable=W0703
            error = f"Error on Query Row: {exc}"
        finally:
            return result, error  # pylint: disable=W0150

    async def fetch_one(  # pylint: disable=W0221
        self,
        cql: str,
        params: Optional[tuple] = None,
    ) -> ResultSet:
        try:
            result = await self.execute_future(cql, params).one()
        except RuntimeError as exc:
            raise DriverError(f"Runtime on Query Row Error: {exc}") from exc
        except Exception as exc:
            raise Exception(f"Error on Query Row: {exc}") from exc
        else:
            if result is None:
                raise NoDataFound("Cassandra: No Data was Found")
            return result

    async def fetchrow(self, sentence, params: Optional[list] = None):
        if params is None:
            params = []
        return await self.fetch_one(sentence=sentence, params=params)

    async def execute(  # pylint: disable=W0221
        self,
        cql: str,
        params: Optional[tuple] = None,
        **kwargs,
    ) -> Any:
        result = error = None
        item = await self.get_or_create_prepared(cql)
        prepared = item.prepared
        stmt = prepared.bind(*params)

        try:
            result = await self.execute_future(stmt, **kwargs)
            if not result:
                error = NoDataFound("Cassandra: No Data was Found")
        except ReadTimeout:
            error = "Timeout executing sentences"
        except Exception as exc:  # pylint: disable=W0703
            error = f"Error on Execute: {exc}"
        finally:
            return result, error  # pylint: disable=W0150

    async def execute_many(  # pylint: disable=W0221
        self,
        sentence: str,
        params: Optional[list] = None,
    ) -> Any:
        result = error = None

        batch = BatchStatement(batch_type=BatchType.UNLOGGED)
        for p in params:
            if isinstance(p, dict):
                args = tuple(p.values())
            else:
                args = tuple(p)

            if isinstance(sentence, CassPreparedStatement):
                stmt = sentence
            else:
                stmt = CassSimpleStatement(sentence)
            batch.add(stmt, args)

        try:
            result = await self.execute_future(batch)
        except ReadTimeout:
            error = "Timeout executing sentences"
        except Exception as exc:  # pylint: disable=W0703
            error = f"Error on Execute: {exc}"
        finally:
            return result, error  # pylint: disable=W0150

    ### Model Logic:
    async def column_info(self, table: str, schema: str = None):
        """Column Info.

        Get Meta information about a table (column name, data type and PK).
        Useful to build a DataModel from Querying database.
        Parameters:
        @tablename: str The name of the table (including schema).
        """
        if not schema:
            schema = self._cass_session.keyspace
        cql = f"select column_name as name, type, type as format_type, \
            kind from system_schema.columns where \
                keyspace_name = '{schema}' and table_name = '{table}';"

        try:
            return await self.execute_future(cql)
        except Exception as err:
            info = f"Wrong Table information {table!s}: {err}"
            logger.exception(info)
            raise DriverError(info) from err
