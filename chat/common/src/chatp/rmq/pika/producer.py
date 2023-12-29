from typing import Optional, Union

from aio_pika.abc import DeliveryMode
from aio_pika.message import Message
from aio_pika.robust_channel import RobustChannel
from aio_pika.robust_exchange import RobustExchange

from .model import StaticTopology, BrokerMessage


class RMQProducer:
    __slots__ = (
        "topo",
        "write_channel",
        "write_exchange",
    )

    def __init__(self, topo: StaticTopology) -> None:
        self.topo = topo
        self.write_channel: RobustChannel
        self.write_exchange: RobustExchange

    @property
    def exchange_name(self):
        return self.topo.exchange_name

    @property
    def exchange_type(self):
        return self.topo.exchange_type

    @property
    def routing_key(self):
        return self.topo.routing_key

    async def bind_queue(self, queue_name: str, routing_key: Optional[str] = None):
        queue = await self.write_channel.declare_queue(queue_name)
        await queue.bind(exchange=self.exchange_name, routing_key=routing_key)

    async def startup(self, write_channel: RobustChannel) -> None:
        self.write_exchange = await write_channel.declare_exchange(
            self.exchange_name,
            type=self.exchange_type,
        )
        self.write_channel = write_channel

    async def kick(
        self,
        message: BrokerMessage,
        routing_key: Optional[str] = None,
        timeout: Union[int, float] = 5,
    ) -> None:
        headers = message.extra_info or {}
        if (task_name := message.task_name) is not None:
            headers["task_name"] = task_name

        await self.write_exchange.publish(
            Message(
                message.entity,
                headers=headers,
                message_id=message.task_id,
                user_id=message.user_id,
                app_id=message.app_id,
                delivery_mode=DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key or self.routing_key,
            timeout=timeout,
        )
