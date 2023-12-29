from typing import Optional

from .backend import AsyncMyBackend, AsyncMyConnectionPool


class DbBaseService:
    IDLE_TIMEOUT: int = 300

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5432,
        user: str = "garvenlee",
        password: str = "121380316",
        db: str = "chatApp",
        schema_dir: Optional[str] = None,
        **kwargs
    ) -> None:
        # mysql 3306 postgres 5432
        self._backend = backend = AsyncMyBackend(
            host=host,
            port=port,
            user=user,
            password=password,
            db=db,
            schema_dir=schema_dir,
            **kwargs,
        )
        self._conn_pool = AsyncMyConnectionPool(backend)

    async def __aenter__(self):
        await self._backend.initialize()
        await self._conn_pool.initialize()
        return self

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        await self._conn_pool.close()
        await self._backend.close()


if __name__ == "__main__":
    pass
