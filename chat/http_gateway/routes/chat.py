from logging import getLogger
from typing import Optional, cast
from blacksheep.settings.json import json_settings
from blacksheep.messages import Request, Response
from blacksheep.contents import Content, StreamedContent
from blacksheep.server.responses import text

from chatp.rpc.model import *
from chatp.manager.grpc_client import GrpcClientManager
from chatp.proto.services.transfer.cass_storage_pb2 import (
    CassSessionRequest,
    CassSessionReply,
)
from chatp.proto.services.transfer.downstream_pb2 import (
    PullInboxRequest,
    PullInboxReply,
    READ_MODEL_SUCCESS,
    READ_MODEL_TIMEOUT,
    READ_MODEL_FAILED,
)
from rpc.transfer_service import DownstreamTransferService
from rpc.cass_storage_service import CassMessageService

logger = getLogger("ChatView")
logger.setLevel(10)


async def pull_inbox(request: Request, grpc_manager: GrpcClientManager) -> Response:
    form = await request.form()
    last_max_msg_id = form.get("last_max_msg_id")
    if last_max_msg_id is None:
        return text("Missing required field in the form", 400)

    try:
        last_max_msg_id = int(last_max_msg_id)
    except ValueError:
        return text("Invalid field value in the form", 400)

    service: Optional[DownstreamTransferService] = grpc_manager.find_service(
        "DownstreamTransferService"
    )
    if service is None:
        logger.warning("DownstreamTransferService is unavailable temporarily now")
        return Response(500)

    result: CallResult = await service.PullInboxMsg(
        PullInboxRequest(uid=request.scope["uid"], received_max_msg_id=last_max_msg_id),
        timeout=8,
    )
    if (grpc_status := result.status) is GRPC_SUCCESS:
        data: PullInboxReply = result.data
        if (status := data.status) is READ_MODEL_SUCCESS:
            json_data = []
            if messages := data.messages:
                json_data_append = json_data.append
                for server_msg in messages:
                    msg_data = server_msg.data
                    json_data_append(
                        {
                            "message_id": server_msg.message_id,
                            "session_id": msg_data.session_id,
                            "sender_id": msg_data.sender_id,
                            "text": msg_data.text,
                        }
                    )
            return Response(
                status=200,
                content=Content(
                    b"application/json",
                    json_settings.dumps({"data": json_data}).encode("utf-8"),
                ),
            )
        elif status is READ_MODEL_TIMEOUT:
            logger.warning("DownstreamTransferService is busy")
            return text("Sorry, timeout, try later")
        elif status is READ_MODEL_FAILED:
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


async def pull_sessions(request: Request, grpc_manager: GrpcClientManager) -> Response:
    json_data: dict = await request.json()
    session_ids = json_data.get("session_ids")  # batch this in the front
    if session_ids is None or not isinstance(session_ids, list):
        return Response(400)

    service: CassMessageService = grpc_manager.find_service("CassMessageService")
    if service is None:
        logger.warning("CassMessageService is unavailable temporarily now")
        return Response(500)

    async def data_generator() -> bytes:
        json_dumps = json_settings.dumps
        async for data in service.ReadSession(
            CassSessionRequest(session_ids=session_ids),
            wait_for_ready=True,
        ):
            data = cast(CassSessionReply, data)
            messages = data.messages
            json_data = [None] * len(messages)
            for seq, server_msg in enumerate(messages):
                msg_data = server_msg.data
                json_data[seq] = {
                    "message_id": server_msg.message_id,
                    "sender_id": msg_data.sender_id,
                    "text": msg_data.text,
                }
            yield json_dumps({"data": json_data}).encode("ascii")

    return Response(
        200, content=StreamedContent(b"application/grpc-bytes", data_generator)
    )
