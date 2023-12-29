from random import choice
from logging import getLogger
from typing import Iterator
from collections import deque
from itertools import repeat, cycle
from functools import partial
from asyncio import wait, create_task

from aio_pika.robust_channel import RobustChannel
from aio_pika.robust_connection import RobustConnection, connect_robust

from .model import InterfaceError, TooManyChannels

logger = getLogger("RabbitConnector")


class RMQConnection:
    __slots__ = "_conn", "_channels", "_max_channels"

    def __init__(self, conn: RobustConnection, max_channels: int):
        self._conn = conn
        self._channels: deque[RobustChannel] = deque(maxlen=max_channels)
        self._max_channels = max_channels

    @property
    def num_channels(self):
        return len(self._channels)

    async def create_channel(self):
        if self.num_channels < self._max_channels:
            channel = await self._conn.channel()
            self._channels.append(channel)
            return channel

        raise TooManyChannels()

    def get_channel(self):
        if channels := self._channels:
            return choice(channels)

        raise InterfaceError("Attempt to get a channel from a bare connection.")

    async def close(self):
        channels, self._channels = self._channels, None
        if channels:  # TODO ReCheck Here
            to_cancel = [create_task(channel.close()) for channel in channels]
            await wait(to_cancel)

        conn, self._conn = self._conn, None
        await conn.close()


class RMQConnector:
    def __init__(
        self,
        max_connections: int,
        max_channels: int,
        **conn_kwargs,
    ):
        self.max_connections = max_connections
        self.max_channels = max_channels
        self.conn_kwargs = conn_kwargs

        self._connections: set[RMQConnection] = set()
        self._conn_cycle: Iterator[RMQConnection]

    async def initialize(self):
        connections = self._connections
        connections_add = connections.add
        connect_factory = partial(connect_robust, **self.conn_kwargs)
        for _ in repeat(None, self.max_connections):
            conn = await connect_factory()
            connections_add(RMQConnection(conn, self.max_channels))
        self._conn_cycle = cycle(connections)

    async def get_channel(self):
        conn = next(self._conn_cycle)
        if conn.num_channels < self.max_channels:  # per conn
            return await conn.create_channel()
        else:
            return conn.get_channel()

    async def close(self):
        connections, self._connections = self._connections, None
        tasks = [create_task(conn.close()) for conn in connections]
        await wait(tasks)
