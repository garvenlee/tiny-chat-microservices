from typing import Optional
from chatp.database.cassandra.driver.sylla import AsyncSyllaBackend
from chatp.database.cassandra.session.sylla import AsyncSyllaSession
from chatp.database.cassandra.executor import BaseExecutor
from chatp.database.model import BatchType


class MessageExecutor(BaseExecutor):
    pool: AsyncSyllaBackend

    async def write_session(
        self,
        cql: str,
        session: AsyncSyllaSession,
        *,
        channel_id: int,
        message_id: int,
        sender_seq: int,
        sender_id: int,
        receiver_id: int,
        content: str,
        bucket: int = 0,
    ):
        return await session.execute(
            cql,
            {
                "channel_id": channel_id,
                "bucket": bucket,
                "message_id": message_id,
                "sender_seq": sender_seq,
                "sender_id": sender_id,
                "receiver_id": receiver_id,
                "content": content,
            },
        )

    async def write_inbox(
        self,
        cql: str,
        session: AsyncSyllaSession,
        *,
        channel_id: int,
        message_id: int,
        sender_seq: int,
        sender_id: int,
        receiver_id: int,
        content: str,
    ):
        return await session.execute(
            cql,
            {
                "channel_id": channel_id,
                "message_id": message_id,
                "sender_seq": sender_seq,
                "sender_id": sender_id,
                "receiver_id": receiver_id,
                "content": content,
            },
        )

    async def write_outbox(
        self,
        cql: str,
        session: AsyncSyllaSession,
        *,
        channel_id: int,
        message_id: int,
        sender_seq: int,
        sender_id: int,
        receiver_id: int,
        content: str,
    ):
        return await session.execute(
            cql,
            {
                "channel_id": channel_id,
                "message_id": message_id,
                "sender_seq": sender_seq,
                "sender_id": sender_id,
                "receiver_id": receiver_id,
                "content": content,
            },
        )

    async def write_read_model(
        self,
        batch_type: BatchType.LOGGED,
        *,
        channel_id: int,
        message_id: int,
        sender_seq: int,
        sender_id: int,
        receiver_id: int,
        content: str,
    ):
        queries = self._queries
        inserted_item = {
            "channel_id": channel_id,
            "message_id": message_id,
            "sender_seq": sender_seq,
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "content": content,
        }

        session: AsyncSyllaSession = self.session
        async with session.execute_batch(batch_type) as batch:
            await batch.add_statement(queries["write_inbox"], inserted_item)
            await batch.add_statement(queries["write_outbox"], inserted_item)
        return batch.result

    async def read_inbox(
        self,
        cql: str,
        session: AsyncSyllaSession,
        *,
        receiver_id: int,
        max_recv_msg_id: int,
    ):
        return await session.execute(
            cql,
            {
                "receiver": receiver_id,
                "msg_id": max_recv_msg_id,
            },
        )

    async def read_outbox(
        self,
        cql: str,
        session: AsyncSyllaSession,
        *,
        sender_id: int,
        max_send_msg_id: int,
    ):
        return await session.execute(
            cql,
            {
                "sender": sender_id,
                "msg_id": max_send_msg_id,
            },
        )

    # per message 30B, sender_seq & server_seq 16B -> 50B
    # 200 messages -> 1MB
    async def read_session(
        self,
        cql: str,
        session: AsyncSyllaSession,
        *,
        session_id: int,
        page_size: int = 200,
    ):
        return await session.execute_with_state(
            cql, {"session_id": session_id}, page_size=page_size
        )


class DbService:
    def __init__(
        self,
        schema_dir: str = "./cql/schema",
        query_dir: str = "./cql/query",
        *,
        username: str,
        password: str,
        host: str | list[str],
        port: int = 9042,
        keyspace: Optional[str] = None,
        **extra_kwargs,
    ):
        """
        extra_kwargs:
            connect_timeout: int, default 5
            request_timeout: int, default 12
        """

        executor = MessageExecutor(schema_dir, query_dir)

        pool = AsyncSyllaBackend(
            conn_params={
                "host": host,
                "port": port,
                "username": username,
                "password": password,
                "keyspace": keyspace,
            },
            **extra_kwargs,
        )
        executor.bind_pool(pool)

        self.executor = executor
        self._pool = pool

    async def __aenter__(self):
        await self.executor.initialize()
        return self

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        await self._pool.close()
