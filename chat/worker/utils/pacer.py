from logging import getLogger
from enum import IntEnum
from typing import Optional
from collections import defaultdict

from attrs import define, field
from asyncio import Lock

from chatp.redis.model import REDIS_SUCCESS
from chatp.redis.client import RedisClient

logger = getLogger("MessagePacer")
logger.setLevel(10)


@define(slots=True)
class DeliveryInfo:
    next_delivery_id: int = 0  # delivery_id starts from 1
    delivery_ids: dict[int, int] = field(factory=dict)
    lock: Lock = field(factory=Lock)
    redis_key: Optional[str] = None

    @property
    def initialized(self):
        return self.next_delivery_id > 0


class FilterState(IntEnum):
    NEW_ITEM = 0
    NEW_VERSION = 1  # design?
    CAN_IGNORE = 2
    RETRY_REQUIRED = 3


class MessagePacer:
    __slots__ = "cache", "redis_client"

    def __init__(self, redis_client: RedisClient):
        # TODO may make it one LRUCache
        # sender_id : DeliveryInfo  
        self.cache: defaultdict[int, DeliveryInfo] = defaultdict(DeliveryInfo)
        self.redis_client = redis_client

    async def filter_or_not(
        self, sender_id: int, delivery_id: int, message_id: int
    ) -> FilterState:
        info = self.cache[sender_id]
        next_delivery_id = info.next_delivery_id
        if lock_acquired := not info.initialized:
            await info.lock.acquire()  # new session handled by this consumer

        if info.initialized:
            if lock_acquired:
                info.lock.release()

            if delivery_id >= next_delivery_id:  # start from 1
                ids = info.delivery_ids
                if (handled_msg_id := ids.get(delivery_id)) is None:
                    logger.info(f"New message from sender {sender_id} with delivery_id: {delivery_id}")
                    ids[delivery_id] = message_id  # HANDLING or HANDLED
                    return FilterState.NEW_ITEM

                # Ignore this message anyway
                # TODO Perhaps add message_version in table schema later
                if handled_msg_id >> 22 < message_id >> 22:
                    logger.warning(
                        "Found one duplicate message with newer message_id from sender %s, just ignore it: %s", 
                        sender_id, 
                        delivery_id,
                    )
                else:
                    logger.warning(
                        "Found one duplicate message with older message_id from sender %s, just ignore it: %s", 
                        sender_id, 
                        delivery_id,
                    )
            else:
                logger.info("Found one previously handled message with delivery_id[%s] from sender %s", 
                    delivery_id, 
                    sender_id,
                )
            
            return FilterState.CAN_IGNORE

        else:  # never handled it before
            if (redis_key := info.redis_key) is None:
                info.redis_key = redis_key = f"chatp:user:delivery_id:uid:{sender_id}"
            data, status = await self.redis_client.redis_get(redis_key)
            info.lock.release()  # release anyway
            if status is REDIS_SUCCESS:
                info.next_delivery_id = next_delivery_id = int(data) if data else 1
                if delivery_id < next_delivery_id:
                    logger.info("Found one previously handled message with delivery_id[%s] from sender %s", 
                        delivery_id, 
                        sender_id,
                    )
                    return FilterState.CAN_IGNORE

                logger.info(f"New message from sender {sender_id} with delivery_id: {delivery_id}")
                info.delivery_ids[delivery_id] = message_id  # HANDLING or HANDLED
                return FilterState.NEW_ITEM
            else:
                return FilterState.RETRY_REQUIRED

    async def on_handled_new_item(
        self, sender_id: int, delivery_id: int, message_id: int
    ):
        info = self.cache[sender_id]
        ids = info.delivery_ids
        if delivery_id == info.next_delivery_id:
            delivery_id += 1
            while delivery_id in ids:
                delivery_id += 1
            info.next_delivery_id = delivery_id
            async with info.lock:
                _, status = await self.redis_client.redis_set(
                    info.redis_key, str(delivery_id)
                )
            if status is REDIS_SUCCESS:
                logger.info(f"Redis set max_local_id: {delivery_id}")
                return
            else: # then, next time to set it
                logger.warning("Redis set max_local_id failed")
