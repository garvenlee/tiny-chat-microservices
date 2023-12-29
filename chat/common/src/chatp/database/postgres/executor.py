from __future__ import annotations

from time import monotonic
from functools import partial, wraps, update_wrapper
from typing import Dict, Set, Type, Optional, cast
from contextlib import asynccontextmanager

from ..builder import schema_builder
from ..model import ExecutionResult
from .backend import AsyncMyConnectionPool, AsyncMyConnection

# from types import MethodType, MethodWrapperType, MethodDescriptorType


def transaction(
    wrapped,
    isolation: str = "read_committed",
    readonly: bool = False,
    deferrable: bool = False,
):
    @wraps(wrapped)
    def __inner_impl(*args, **kwargs):
        kwargs["use_transaction"] = True
        kwargs["transaction_setting"] = (
            isolation,
            readonly,
            deferrable,
        )
        return wrapped(*args, **kwargs)

    return __inner_impl


def time_reserve(
    reserve: float = 0.01,  # at least 100ms, reserve for db operation,
):
    def wrapper(wrapped):
        @wraps(wrapped)
        async def _inner_impl(
            self: "BaseExecutor",
            cached_sql: str,  # auto inject
            db_pool: AsyncMyConnectionPool,  # auto inject
            *,
            timeout: float,
            use_transaction: bool = False,
            **kwargs,
        ) -> tuple[Optional[ExecutionResult], float]:
            result = None
            checkpoint = monotonic()
            if (conn := await db_pool.acquire(timeout)) is not None:
                timeout -= monotonic() - checkpoint
                if timeout >= reserve:
                    try:
                        if use_transaction:
                            transaction_setting = kwargs.pop("transaction_setting")
                            async with conn.transaction(*transaction_setting):
                                result = await wrapped(
                                    self,  # executor
                                    conn,
                                    sql=cached_sql,
                                    timeout=timeout,
                                    **kwargs,
                                )
                        else:
                            result = await wrapped(
                                self,  # executor
                                conn,
                                sql=cached_sql,
                                timeout=timeout,
                                **kwargs,
                            )
                    finally:
                        await db_pool.release(conn)
                else:
                    await db_pool.release(conn)
            return result, monotonic() - checkpoint

        _inner_impl.__name__ = f"{_inner_impl.__name__}__with_reserve"
        return _inner_impl

    return wrapper


def without_reserve(wrapped):
    @wraps(wrapped)
    async def _inner_impl(
        self: "BaseExecutor",
        cached_sql: str,  # auto inject
        connection: AsyncMyConnection,  # user arg
        *,
        timeout: float,
        **kwargs,
    ) -> tuple[ExecutionResult, float]:
        checkpoint = monotonic()
        result = await wrapped(
            self,  # executor
            connection,
            sql=cached_sql,
            timeout=timeout,
            **kwargs,
        )
        return result, monotonic() - checkpoint

    _inner_impl.__name__ = f"{_inner_impl.__name__}__without_reserve"
    return _inner_impl


class BaseExecutor:
    """
    Responsible for being the interface between the DB and the application
    """

    _registry: Set[Type[BaseExecutor]] = set()
    _queries: Dict[str, str] = {}
    _initialized: bool

    db_pool: AsyncMyConnectionPool

    def __init_subclass__(cls) -> None:
        BaseExecutor._registry.add(cls)

    def __init__(self, schema_dir: str, query_dir: str) -> None:
        self.schema_dir = schema_dir
        self.query_dir = query_dir
        self._initialized = False

    def bind_pool(self, db_pool: AsyncMyConnectionPool):
        self.db_pool = db_pool

    @asynccontextmanager
    async def borrow_connection(self, timeout: float):
        db_pool = self.db_pool
        conn = await db_pool.acquire(timeout)
        try:
            yield conn
        finally:
            if conn is not None:
                await db_pool.release(conn)

    async def initialize(self):
        if self._initialized:
            return

        if (pool := getattr(self, "db_pool", None)) is None:
            raise Exception(
                "You must call `executor.bind_pool` method to set `db_pool` attribute."
            )

        pool = cast(AsyncMyConnectionPool, pool)
        query_dir = self.query_dir
        cls = self.__class__

        for name, schema in schema_builder(f"{query_dir}/*.sql"):
            cls._queries[name] = schema
            # getattr get cls's plain function definition
            # when cls's instance call .meth_name, then will convey `self` into it

            # plain version impl
            original_func: Optional[function] = getattr(cls, name, None)
            if original_func is not None:
                if not original_func.__name__.endswith("__with_reserve"):
                    original_func = without_reserve(original_func)
                    wrapper = partial(original_func, self, schema)
                else:
                    wrapper = partial(original_func, self, schema, pool)
                setattr(
                    self, name, update_wrapper(wrapper, original_func)
                )  # inject query sql

            # batch version impl
            func_in_batch_version: Optional[function] = getattr(
                cls, f"{name}_in_batch", None
            )
            if func_in_batch_version is not None:
                if not func_in_batch_version.__name__.endswith("__with_reserve"):
                    original_func = without_reserve(original_func)
                wrapper = partial(func_in_batch_version, self, schema)
                setattr(self, name, update_wrapper(wrapper, func_in_batch_version))

        if not cls._queries:
            raise Warning(
                f"[{cls.__name__}] There is no sql definition under directory {query_dir}."
            )

        await pool.initialize()  # if needs
        await pool.backend.create_table(self.schema_dir)

        self._initialized = True
