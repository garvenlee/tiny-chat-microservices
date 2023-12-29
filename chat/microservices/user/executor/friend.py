from time import monotonic
from typing import Optional

from chatp.database.postgres.executor import BaseExecutor, time_reserve, transaction
from chatp.database.postgres.backend import AsyncMyConnection
from chatp.database.model import ExecutionResult, DB_SUCCESS
from chatp.database.exceptions import TransactionFailed


# when Interpretor builds this class,
#   1.load queries from sql files
#   2.wrapper some meths with the corresponding query
class FriendExecutor(BaseExecutor):
    @time_reserve(reserve=0.1)  # acquire connection internally
    async def create_friend_request(
        self,
        connection: AsyncMyConnection,
        *,
        request_id: int,
        address_id: int,
        request_msg: Optional[str],
        **kwargs,
    ) -> Optional[tuple[ExecutionResult, float]]:
        return await connection.create(
            values=(request_id, address_id, request_msg),
            returning=True,
            **kwargs,
        )

    async def respond_friend_request(
        self,
        connection: AsyncMyConnection,
        *,
        request_id: int,
        address_id: int,
        action: str,
        **kwargs,
    ) -> tuple[ExecutionResult, float]:
        return await connection.update(
            values=(action, request_id, address_id), **kwargs
        )

    def _friend_request_helper(action: str, name: str):
        async def _inner_impl(
            self: "FriendExecutor",
            request_id: int,
            address_id: int,
            timeout: float,
            **kwargs,
        ) -> Optional[ExecutionResult]:
            checkpoint = monotonic()
            async with self.borrow_connection(timeout) as connection:
                if connection is not None:
                    timeout -= monotonic() - checkpoint
                    return await self.respond_friend_request(
                        connection,
                        request_id=request_id,
                        address_id=address_id,
                        action=action,
                        timeout=timeout,
                        **kwargs,
                    )

        _inner_impl.__name__ = name
        _inner_impl.__qualname__ = f"FriendExecutor.{name}"
        return _inner_impl

    reject_friend_request = _friend_request_helper("Rejected", "reject_friend_request")
    ignore_friend_request = _friend_request_helper("Ignored", "ignore_friend_request")
    revoke_friend_request = _friend_request_helper("Revoked", "revoke_friend_request")
    accept_friend_request = _friend_request_helper("Accepted", "accept_friend_request")

    # session id - old impl(ver1 & ver2 needs to send back the session_id to A & B)
    # ver1: uuid4 was auto-generated in psql
    # ver2: snowflake id was created locally via unix sock
    # ver3: created via grpc before message was published to MQ (consistency)
    # TODO A request B & B request A at the same time?
    # TODO optimize: relationship already existed before
    @transaction
    @time_reserve(reserve=3)
    async def create_friend(
        self,
        connection: AsyncMyConnection,
        *,
        request_id: int,
        address_id: int,
        session_id: int,
        timeout: float,
        **kwargs,
    ) -> None:
        checkpoint = monotonic()

        result = await connection.create(  # 8ms
            values=(request_id, address_id, session_id),
            returning=True,  # fetchrow
            timeout=timeout,
            **kwargs,
        )
        if (status := result.status) is not DB_SUCCESS:
            raise TransactionFailed(status)

        ckpt2 = monotonic()
        print(f"transaction 1 consumes: {ckpt2 - checkpoint}")

        result, delay = await self.respond_friend_request(  # 250ms
            connection,
            request_id=request_id,
            address_id=address_id,
            action="Accepted",
            timeout=timeout - (ckpt2 - checkpoint),
        )
        if result.status is not DB_SUCCESS:
            raise TransactionFailed(status)

        print(f"transaction 2 consumes: {delay}")

    async def respond_friend(
        self,
        connection: AsyncMyConnection,
        *,
        owner_id: int,
        friend_id: int,
        action: str,
        **kwargs,
    ):
        return connection.update(values=(action, owner_id, friend_id), **kwargs)

    def _friend_helper(action: str, name: str):
        async def _inner_impl(
            self: "FriendExecutor",
            owner_id: int,
            friend_id: int,
            timeout: float,
            **kwargs,
        ) -> Optional[ExecutionResult]:
            checkpoint = monotonic()
            async with self.borrow_connection(timeout) as connection:
                if connection is not None:
                    timeout -= monotonic() - checkpoint
                    return await self.respond_friend(
                        connection,
                        owner_id=owner_id,
                        friend_id=friend_id,
                        action=action,
                        timeout=timeout,
                        **kwargs,
                    )

        _inner_impl.__name__ = name
        _inner_impl.__qualname__ = f"FriendExecutor.{name}"
        return _inner_impl

    delete_friend = _friend_helper("Delected", "delete_friend")
    block_friend = _friend_helper("Blocked", "block_friend")

    @time_reserve(reserve=1)
    async def get_friends(
        self,
        connection: AsyncMyConnection,
        *,
        owner_id: int,
        **kwargs,
    ):
        return await connection.read(
            values=(owner_id,),
            all=True,
            **kwargs
        )
