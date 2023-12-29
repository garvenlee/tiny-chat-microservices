from logging import getLogger
from functools import partial
from typing import Optional, Callable

from asyncio import BaseEventLoop, sleep, get_running_loop
from anyio import fail_after
from acsylla.base import (
    Result,
    Session as SyllaSession,
    Statement as SyllaStatement,
    PreparedStatement as SyllaPreparedStatement,
)
from acsylla.factories import (
    create_batch_unlogged,
    create_batch_logged,
    create_batch_counter,
    create_statement as create_sylla_statement,
)

from chatp.database.model import CachedStatement, BatchType
from ..base import AsyncSessionBase

logger = getLogger("AsyncSyllaSession")


class AsyncResultGenerator:
    __slots__ = "session", "statement", "task_factory"

    def __init__(
        self,
        session: SyllaSession,
        statement: SyllaStatement,
        *,
        task_factory: Callable,
    ):
        self.session = session
        self.statement = statement
        self.task_factory = task_factory

    async def __aiter__(self):
        session, statement = self.session, self.statement
        task_factory = self.task_factory
        coro_func = partial(session.execute, statement)

        result = await coro_func()
        while True:
            if result.has_more_pages():
                statement.set_page_state(result.page_state())
                next_page = task_factory(coro_func())
                await sleep(0)
            else:
                next_page = None

            for row in result:
                yield dict(row)

            if next_page is not None:
                result = await next_page
            else:
                break


BATCH_MAPPING = {
    BatchType.UNLOGGED: create_batch_unlogged,
    BatchType.LOGGED: create_batch_logged,
    BatchType.COUNTER: create_batch_counter,
}


class AsyncSyllaBatch:
    __slots__ = "_session", "_sylla_batch", "_result"

    def __init__(
        self,
        session: "AsyncSyllaSession",
        batch_type: BatchType,
        *,
        timeout: Optional[float] = None,
        execution_profile: Optional[str] = None,
    ):
        self._session = session
        self._sylla_batch = BATCH_MAPPING[batch_type](timeout, execution_profile)

        self._result: Optional[Result] = None

    @property
    def result(self):
        return self._result

    async def add_statement(self, cql: str, params: Optional[dict]):
        item: CachedStatement = await self._session.get_or_create_prepared(cql)
        stmt: SyllaStatement = item.statement
        stmt.bind_dict(params)
        self._sylla_batch.add_statement(stmt)

    async def __aenter__(self):
        return self

    async def __aexit__(self):
        self._result = await self._session._sylla_session.execute_batch(
            self._sylla_batch
        )


class AsyncSyllaSession(AsyncSessionBase):
    __slots__ = "_loop", "_sylla_session", "_cached_statements", "_cached_prepared"

    def __init__(self, session: SyllaSession, *, loop: Optional[BaseEventLoop] = None):
        if loop is None:
            loop = get_running_loop()

        self._loop = loop
        self._sylla_session: SyllaSession = session

        self._cached_statements: dict[str, SyllaStatement] = dict()
        self._cached_prepared: dict[str, CachedStatement] = dict()

    async def close(self, timeout: int):
        session, self._sylla_session = self._sylla_session, None
        with fail_after(timeout):
            await session.close()

    def get_or_create_statement(self, cql: str):
        cached_statements = self._cached_statements
        stmt = cached_statements.get(cql)
        if stmt is None:
            stmt = create_sylla_statement(cql)
            cached_statements[cql] = stmt
        return stmt

    async def get_or_create_prepared(self, cql: str, *, timeout: float = 5.0):
        cached_prepared = self._cached_prepared
        item = cached_prepared.get(cql)
        if item is None:
            prepared = await self._sylla_session.create_prepared(cql, timeout)
            item = CachedStatement(cql, prepared, prepared.bind())
            cached_prepared[cql] = item
        return item

    async def query(self, cql: str):
        statement = self.get_or_create_statement(cql)
        return await self._sylla_session.execute(statement)

    async def execute(self, cql: str, params: dict):
        item: CachedStatement = await self.get_or_create_prepared(cql)
        stmt: SyllaStatement = item.statement
        stmt.bind_dict(params)
        return await self._sylla_session.execute(stmt)

    async def execute_with_state(
        self,
        cql: str,
        params: dict,
        *,
        page_size: int,
        page_state: Optional[bytes] = None,
        execution_profile: Optional[str] = None,
    ):
        item = await self.get_or_create_prepared(cql)
        prepared: SyllaPreparedStatement = item.prepared
        stmt = prepared.bind(page_size, page_state, execution_profile)
        stmt.bind_dict(params)
        return await self._sylla_session.execute(stmt)

    def execute_batch(
        self,
        batch_type: BatchType.UNLOGGED,
        *,
        timeout: Optional[float] = None,
        execution_profile: Optional[str] = None,
    ):
        return AsyncSyllaBatch(
            self, batch_type, timeout=timeout, execution_profile=execution_profile
        )

    async def find(self, cql: str, *, params: dict, page_size: int = 10):
        item = await self.get_or_create_prepared(cql)
        prepared: SyllaPreparedStatement = item.prepared
        stmt = prepared.bind(page_size)  # adjust page_size & exec_profile
        stmt.bind_dict(**params)
        return AsyncResultGenerator(
            self._sylla_session,
            stmt,
            task_factory=self._loop.create_task,
        )
