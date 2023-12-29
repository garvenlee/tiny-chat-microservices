class AsyncSessionBase:
    pass


class AsyncBackendBase:
    session: AsyncSessionBase

    async def initialize(self):
        raise NotImplementedError

    async def close(self, timeout):
        raise NotImplementedError

    async def create_table(self, schema_dir: str) -> None:
        raise NotImplementedError
