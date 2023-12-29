from logging import getLogger
from typing import Optional
from chatp.utils.types import PartialMethodType
from chatp.rpc.grpc_service import GrpcStub
from algo.model import RefreshTokenKey


logger = getLogger("AuthHandler")


async def store_refresh_token(
    uid: int, refresh_token: str, redis_set: PartialMethodType[[], GrpcStub]
) -> bool:
    # logger.info("published a writeTask to redis_service")
    # return await redis_set().set(key=str(RefreshTokenKey(uid)), value=refresh_token)
    data, status = await redis_set(key=str(RefreshTokenKey(uid)), value=refresh_token)
    return data


async def retrieve_refresh_token(
    uid: int, redis_get: PartialMethodType[[], GrpcStub]
) -> Optional[str]:
    # logger.info("published a readTask to redis_service")
    # return await redis_get().get(key=str(RefreshTokenKey(uid)))
    data, status = await redis_get(key=str(RefreshTokenKey(uid)))
    return data
