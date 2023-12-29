from time import monotonic
from logging import getLogger
from typing import Optional, cast
from asyncio import create_task, sleep, Task
from aetcd.client import Client

logger = getLogger("ServiceManager")
logger.setLevel(10)


class RLease:
    default_ttl: int = 10

    __slots__ = (
        "ttl",
        "aetcd_client",
        "aetcd_lease",
        "lease_id",
        "old_lease_ids",
        "refresh_task",
        "last_refresh_time",
        "refresh",
        "revoke",
        "info",
    )

    def __init__(self, ttl: int, client: Client):
        if ttl <= 0:
            ttl = self.__class__.default_ttl
        self.ttl = ttl
        self.aetcd_client = client

        self.lease_id: int = -1
        self.old_lease_ids = set()
        self.refresh_task: Optional[Task] = None

        self.refresh = client.refresh_lease
        self.revoke = client.revoke_lease
        self.info = client.get_lease_info

    async def keepalive(self):
        self.last_refresh_time = monotonic()  # startpoint of lease itself

        logger.info("[EtcdLease] New one lease...")
        ttl = self.ttl
        self.aetcd_lease = lease = await self.aetcd_client.lease(ttl)
        self.lease_id = lease_id = lease.id
        self.refresh_task = create_task(self.refresh_lease(lease_id, period=ttl // 2))
        return lease_id

    async def clear(self):
        if (task := self.refresh_task) is not None:
            self.refresh_task = None

            task = cast(Task, task)
            task.cancel()

            await self.revoke(self.lease_id)
            self.lease_id = -1

    async def refresh_lease(self, lease_id: int, *, period: int):
        refresh = self.refresh
        while True:
            # stream_stream meth but only request once with request_timeout
            # so this will raise ConnectionTimeoutError(ClientError),
            # then it means the service is down in etcd's view, and service supplier
            # must register itself again
            reply = await refresh(
                lease_id
            )  # let registered key closed with lease itself
            self.last_refresh_time = monotonic()  # update if succeed
            # logger.debug(
            #     f"[EtcdLease] refresh_lease got a reply: {reply.ID} / {self.lease_id}"
            # )
            await sleep(period)
