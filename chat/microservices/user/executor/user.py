from chatp.database.postgres.executor import BaseExecutor, time_reserve
from chatp.database.postgres.backend import AsyncMyConnection


class UserExecutor(BaseExecutor):
    @time_reserve(reserve=0.1)
    async def register_user(
        self,
        connection: AsyncMyConnection,
        *,
        email: str,
        password: str,
        username: str,
        **kwargs,
    ):
        return await connection.create(
            values=(email, password, username),
            returning=True,
            **kwargs,
        )

    @time_reserve(reserve=0.01)
    async def login_user(self, connection: AsyncMyConnection, *, email: str, **kwargs):
        return await connection.read(values=(email,), **kwargs)

    @time_reserve(reserve=0.01)
    async def query_user(self, connection: AsyncMyConnection, *, email: str, **kwargs):
        return await connection.read(values=(email,), **kwargs)

    @time_reserve(reserve=0.1)
    async def confirm_user(self, connection: AsyncMyConnection, *, seq: int, **kwargs):
        return await connection.update(values=(seq,), **kwargs)
