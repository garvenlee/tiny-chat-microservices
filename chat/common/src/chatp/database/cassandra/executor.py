from typing import Optional, cast
from functools import partial, update_wrapper

from .base import AsyncBackendBase
from ..builder import schema_builder


class BaseExecutor:
    _initialized: bool
    _queries: dict[str, str] = {}

    pool: AsyncBackendBase

    def __init__(self, schema_dir: str, query_dir: str) -> None:
        self.schema_dir = schema_dir
        self.query_dir = query_dir
        self._initialized = False

    def bind_pool(self, pool: AsyncBackendBase):
        self.pool = pool

    @property
    def session(self):
        return self.pool.session

    async def initialize(self):
        if self._initialized:
            return

        if (pool := getattr(self, "pool", None)) is None:
            raise Exception(
                "You must call `executor.bind_session` method to set `session` attribute."
            )

        pool = cast(AsyncBackendBase, pool)
        query_dir = self.query_dir
        cls = self.__class__

        pending_info = {}
        for name, cql in schema_builder(f"{query_dir}/*.cql"):
            cls._queries[name] = cql
            # getattr get cls's plain function definition
            # when cls's instance call .meth_name, then will convey `self` into it

            # plain version impl
            original_func: Optional[function] = getattr(cls, name, None)
            if original_func is not None:
                pending_info[name] = (original_func, cql)

        if not cls._queries:
            raise Warning(
                f"[{cls.__name__}] There is no cql definition under directory {query_dir}."
            )

        if not pending_info:
            raise Warning(
                f"[{cls.__name__}] There is no corresponding function definition in {cls.__name__}."
            )

        session = await pool.initialize()
        await pool.create_table(self.schema_dir)

        for name, item in pending_info.items():
            original_func, cql = item
            # inject query cql and session
            wrapper = partial(original_func, self, cql, session)
            setattr(self, name, update_wrapper(wrapper, original_func))

        self._initialized = True
