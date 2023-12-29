from uuid import UUID
from logging import getLogger
from dataclasses import dataclass

from blacksheep.settings.json import json_settings
from blacksheep.messages import Response
from blacksheep.contents import Content
from blacksheep.server.responses import text, json
from blacksheep.server.bindings import FromForm, Request

from rmq.service import RMQService
from rpc.user_service import UserService
from utils.background_tasks import BackgroundTaskManager
from utils.setting import ServerSetting

from chatp.rpc.model import *
from chatp.manager.grpc_client import GrpcClientManager
from chatp.proto.services.friend.friend_pb2 import (
    FriendEvent,
    FriendRequest,
    FriendConfirm,
    RelationLink,
    FriendListReply,
    FRIEND_SUCCESS,
    FRIEND_TIMEOUT,
    FRIEND_FAILED,
    FRIEND_REQUEST,
    FRIEND_CONFIRM,
)

logger = getLogger("FriendView")
logger.setLevel(10)


@dataclass
class FriendRequestForm:
    address_id: int
    request_uid: str
    request_email: str
    request_username: str
    appid: str
    request_msg: Optional[str] = None


@dataclass
class FriendConfirmForm:
    address_id: int
    action: int
    appid: str


async def friend_request(
    request: Request,
    form: FromForm[FriendRequestForm],
    rmq_service: RMQService,
    setting: ServerSetting,
    task_manager: BackgroundTaskManager,
) -> Response:
    request_id = request.scope["uid"]

    value: FriendRequestForm = form.value
    appid = value.appid
    if not appid.startswith(setting.APPID_PREFIX):
        return text("Invalid Request", 400)

    uid = UUID(hex=value.request_uid, version=1).bytes
    username = value.request_username
    email = value.request_email
    if (request_msg := value.request_msg) is None:
        event = FriendEvent(
            evt_tp=FRIEND_REQUEST,
            request=FriendRequest(
                uid=uid,
                username=username,
                email=email,
                link=RelationLink(
                    request_id=request_id, address_id=int(value.address_id)
                ),
            ),
        )
    else:
        event = FriendEvent(
            evt_tp=FRIEND_REQUEST,
            request=FriendRequest(
                uid=uid,
                username=username,
                email=email,
                link=RelationLink(
                    request_id=request_id, address_id=int(value.address_id)
                ),
                request_msg=request_msg,
            ),
        )
    # TODO publish default timeout?
    task_manager.create_task(
        rmq_service.publish_friend_request(
            event.SerializeToString(),
            # user_id=request_id,
            user_id=None,
            app_id=appid,
        )
    )
    return Response(200)


async def friend_confirm(
    request: Request,
    form: FromForm[FriendConfirmForm],
    rmq_service: RMQService,
    setting: ServerSetting,
    grpc_manager: GrpcClientManager,
    task_manager: BackgroundTaskManager,
) -> Response:
    request_id = request.scope["uid"]

    value: FriendRequestForm = form.value
    appid = value.appid
    if not appid.startswith(setting.APPID_PREFIX):
        return text("Invalid Request", 400)

    snowflake_id = 0
    if (action := int(value.action)) == 0:
        snowflake_service = grpc_manager.find_service("SnowflakeService")
        if snowflake_service is None:
            logger.warning("SnowflakeService is unavailable")
            return Response(500)

        result: CallResult = await snowflake_service.flickClock(kind=0, timeout=2)
        if (grpc_status := result.status) is GRPC_SUCCESS:
            snowflake_id = result.data.snowflake_id

        elif grpc_status is GRPC_TIMEOUT:
            return Response(status=504)  # gateway timeout
        else:
            logger.warning(f"\t{result.info}")
            return Response(400)  # Bad Request

    event = FriendEvent(
        evt_tp=FRIEND_CONFIRM,
        confirm=FriendConfirm(
            link=RelationLink(request_id=request_id, address_id=int(value.address_id)),
            action=action,
            session_id=snowflake_id,
        ),
    )
    # TODO publish default timeout?
    task_manager.create_task(
        rmq_service.publish_friend_confirm(
            event.SerializeToString(),
            # user_id=request_id,
            user_id=None,
            app_id=appid,
        )
    )

    # TODO if A request again?
    return json({"session_id": snowflake_id})


async def get_friends(request: Request, grpc_manager: GrpcClientManager) -> Response:
    stub: Optional[UserService] = grpc_manager.find_service(
        "UserService", domain="FriendStub"
    )
    if stub is None:
        logger.warning("UserService/FriendStub domain is unavailable")
        return Response(500)

    result: CallResult = await stub.GetFriendList(seq=request.scope["uid"], timeout=5)
    if (grpc_status := result.status) is GRPC_SUCCESS:
        data: FriendListReply = result.data
        if (status := data.status) is FRIEND_SUCCESS:
            json_data = []
            if friends := data.friends:
                json_data_append = json_data.append
                for info in friends:
                    json_data_append(
                        {
                            "session_id": info.session_id,
                            "seq": info.seq,
                            "uid": UUID(bytes=info.uid, version=1).hex,
                            "username": info.username,
                            "email": info.email,
                            "remark": info.remark or "",
                        }
                    )
            return Response(
                status=200,
                content=Content(
                    b"application/json",
                    json_settings.dumps({"data": json_data}).encode("utf-8"),
                ),
            )
        elif status is FRIEND_TIMEOUT:
            logger.warning("DownstreamTransferService is busy")
            return text("Sorry, timeout, try later", status=504)
        elif status is FRIEND_FAILED:
            return text("Sorry, timeout, please try it again", status=504)
        else:
            return text("Sorry, something wrong, please try it later", status=503)
    elif grpc_status is GRPC_TIMEOUT:
        # maybe service is unavailable
        logger.warning("gateway countered timeout when register user")
        return Response(status=504)  # gateway timeout
    else:
        logger.warning(result.info)
        return Response(status=400)  # Bad Request
