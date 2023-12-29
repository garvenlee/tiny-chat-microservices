from typing import NamedTuple, Optional
from aio_pika.abc import ExchangeType
from aio_pika.message import IncomingMessage


class TooManyChannels(Exception):
    pass


class InterfaceError(Exception):
    pass


class StaticTopology(NamedTuple):
    exchange_type: ExchangeType
    exchange_name: str
    routing_key: Optional[str] = None
    queue_name: str = ""
    # auto_delete: bool = False


class BrokerMessage(NamedTuple):
    entity: bytes

    # validate message source
    user_id: str
    app_id: str

    task_id: Optional[str] = None
    task_name: Optional[str] = None

    reply_to: Optional[str] = None
    # used to filter, default UUID4 in aiormq.basic_publish
    extra_info: Optional[dict[str, str]] = None  # required in application business


# TODO maybe add message filter here (already consumed)
class ConsumerMessage:
    __slots__ = "_message"

    def __init__(self, message: IncomingMessage):
        self._message = message

    @property
    def headers(self):
        return self._message.headers

    @property
    def message_id(self):
        return self._message.message_id

    @property
    def channel(self):
        return self._message.channel

    @property
    def reply_to(self):
        return self._message.reply_to

    async def ack(self, multiple: bool = False):
        try:
            # writer.write may trigger protocol.connection_lost, but dont raise any exc (fast return)
            # writer.drain -> StreamReader.exc is not None -> drain_future will raise it
            # so if conn is lost, here may raise exc
            await self._message.ack(multiple)
            return True
        except OSError:
            return False

    async def reject(self, requeue: bool = True):
        try:
            await self._message.reject(requeue)
            return True
        except OSError:
            return False

    async def nack(self, multiple: bool = False, requeue: bool = True):
        try:
            await self._message.nack(multiple, requeue)
            return True
        except OSError:
            return False
