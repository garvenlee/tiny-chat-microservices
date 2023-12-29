from executor import DbExecutor
from chatp.database.postgres.backend import AsyncMyConnectionPool


class DbService:
    def __init__(
        self,
        schema_dir: str = "./sql/schema",
        query_dir: str = "./sql/query",
        **connect_kwargs,
    ) -> None:
        pool = AsyncMyConnectionPool(**connect_kwargs)

        executor = DbExecutor(schema_dir, query_dir)
        executor.bind_pool(pool)

        self.executor = executor
        self._pool = pool

    async def __aenter__(self):
        await self.executor.initialize()
        return self

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        await self._pool.close()
