from uuid import UUID
from time import monotonic
from logging import getLogger
from dataclasses import dataclass
from blacksheep.settings.json import json_settings
from blacksheep.messages import Response
from blacksheep.contents import Content
from blacksheep.server.responses import json, text
from blacksheep.server.bindings import Request,  FromForm

from rpc.user_service import UserService
from rpc.auth_service import AuthService
from rmq.service import RMQService
from utils.setting import ServerSetting
from utils.background_tasks import BackgroundTaskManager
from utils.email import generate_confirm_message

from chatp.rpc.model import *
from chatp.manager.grpc_client import GrpcClientManager
from chatp.proto.services.user.user_pb2 import (
    USER_DB_TIMEOUT,
    USER_NOT_EXISTS,
    UserQueryReply,
)
from chatp.proto.services.auth.auth_user_pb2 import (
    AUTH_SUCCESS,
    AUTH_TIMEOUT,
    AuthLoginReply,
    AuthRegisterReply,
    AuthRegisterConfirmReply,
    AuthRefreshTokenReply,
    AUTH_INCORRECT_EMAIL,
    AUTH_INCORRECT_PWD,
    AUTH_EXPIRED,
    AUTH_NOT_EXISTS,
    AUTH_ALREADY_EXISTS,
)

logger = getLogger("UserView")
logger.setLevel(10)


@dataclass
class LoginForm:
    email: str
    password: str


@dataclass
class RegisterForm:
    username: str
    email: str
    password: str
    appid: str


# auto deserialize, if failed, then return 400 bad request
async def login(
    _: Request, form: FromForm[LoginForm], grpc_manager: GrpcClientManager
) -> Response:
    value: LoginForm = form.value
    email, password = value.email, value.password

    start = monotonic()
    auth_service: Optional[AuthService] = grpc_manager.find_service("AuthService")
    if auth_service is None:
        logger.warning("Auth Service is unavailable")
        return Response(500)

    result: CallResult = await auth_service.AuthLogin(
        email=email,
        password=password,
        timeout=5,  # up to 5s
    )
    logger.warning(f"one login consume: {monotonic() - start}")
    if (grpc_status := result.status) is GRPC_SUCCESS:
        data: AuthLoginReply = result.data
        if (status := data.status) is AUTH_SUCCESS:
            # logger.info("successfully got tokens and loged in.")
            user = data.user
            response = Response(
                status=200,
                headers=[
                    (b"access_token", data.access_token.encode("utf-8")),
                    (b"refresh_token", data.refresh_token.encode("utf-8")),
                ],
                content=Content(
                    b"application/json",
                    json_settings.dumps(
                        {
                            "seq": user.seq,
                            "uid": UUID(bytes=user.uid, version=1).hex,
                            "username": user.username,
                        }
                    ).encode("utf-8"),
                ),
            )
        elif status is AUTH_TIMEOUT:
            logger.warning("auth timeout")
            response = Response(status=504)  # timeout
        else:
            if (info := data.info) is AUTH_INCORRECT_EMAIL:  # Unauthorized
                info = "incorrect email"
                response = json({"err_code": 0}, status=401)
            elif info is AUTH_INCORRECT_PWD:  # Unauthorized
                info = "incorrect pwd"
                response = json({"err_code": 1}, status=401)
            elif info is AUTH_NOT_EXISTS:
                info = "user not exists"
                response = Response(status=202)
            else:  # unavailable
                info = "unknown error"
                response = Response(status=503)
            logger.info(f"Auth Failed: {info}")
    elif grpc_status is GRPC_TIMEOUT:
        logger.warning("gateway countered timeout when user loged in")
        response = Response(status=504)  # gateway timeout
    else:
        logger.warning(f"\t{result.info}")
        response = json({"info": result.info}, status=400)  # Bad Request

    return response


async def register(
    _: Request,
    form: FromForm[RegisterForm],
    grpc_manager: GrpcClientManager,
    rmq_service: RMQService,
    setting: ServerSetting,
    task_manager: BackgroundTaskManager,
) -> Response:
    value = form.value
    appid = value.appid
    if not appid.startswith(setting.get("APPID_PREFIX")):
        return text("Invalid Request", 400)

    email = value.email
    auth_service: Optional[AuthService] = grpc_manager.find_service("AuthService")
    if auth_service is None:
        logger.warning("Auth Service is unavailable")
        return Response(500)

    result: CallResult = await auth_service.AuthRegister(
        email=email,
        password=value.password,
        username=value.username,
        timeout=8,
    )

    if (grpc_status := result.status) is GRPC_SUCCESS:
        # logger.info("successful grpc call")
        data: AuthRegisterReply = result.data
        if (status := data.status) is AUTH_SUCCESS:
            # logger.info("successfully registered.")
            link = f"http://0.0.0.0:10000/user/register/confirm/{data.token}"
            message = generate_confirm_message(link, email)
            # succeed or failed dont cause response failed
            task_manager.create_task(
                rmq_service.publish_email(message, user_id=None, app_id=appid)
            )
            return Response(status=200)
        elif status is AUTH_TIMEOUT:
            info = "user service is busy, maybe try later"
            logger.warning(info)
            return Response(status=504)  # unavailable
        else:
            if (info := data.info) is AUTH_ALREADY_EXISTS:
                info = "email has been used"
                logger.info(info)
                return Response(status=202)  # Accepted but not handled
            else:
                # Bad Gateway // error response
                logger.warning(info)
                return Response(status=502)
    elif grpc_status is GRPC_TIMEOUT:
        # maybe service is unavailable
        logger.warning("gateway countered timeout when register user")
        return Response(status=504)  # gateway timeout
    else:
        info = result.info
        logger.warning(f"\t{info}")
        return json({"info": info}, status=400)  # Bad Request


async def confirm(request: Request, grpc_manager: GrpcClientManager) -> Response:
    token: str = request.route_values["token"]
    auth_service: Optional[AuthService] = grpc_manager.find_service("AuthService")
    if auth_service is None:
        logger.warning("Auth Service is unavailable")
        return Response(500)

    result: CallResult = await auth_service.AuthRegisterConfirm(token=token, timeout=5)
    if (grpc_status := result.status) is GRPC_SUCCESS:
        data: AuthRegisterConfirmReply = result.data
        if (status := data.status) is AUTH_SUCCESS:
            # TODO maybe set cuckoofilter
            return text("Confirmed Successfully")
        elif status is AUTH_EXPIRED:
            return text("Sorry, this activate link has expired.")
        elif status is AUTH_TIMEOUT:
            return text("Sorry, timeout, please try it again", status=504)
        else:
            return text("Sorry, something wrong, please try it later", status=503)
    elif grpc_status is GRPC_TIMEOUT:
        # maybe service is unavailable
        logger.warning("gateway countered timeout when register user")
        return Response(status=504)  # gateway timeout
    else:
        info = result.info
        logger.warning(f"\t{info}")
        return json({"info": info}, status=400)  # Bad Request


async def refresh_token(request: Request, grpc_manager: GrpcClientManager) -> Response:
    form = await request.form()
    auth_service: Optional[AuthService] = grpc_manager.find_service("AuthService")
    if auth_service is None:
        logger.warning("Auth Service is unavailable")
        return Response(500)

    result: CallResult = await auth_service.AuthRefresh(**form)
    if (grpc_status := result.status) is GRPC_SUCCESS:
        data: AuthRefreshTokenReply = result.data
        if (status := data.status) is AUTH_SUCCESS:
            logger.info("user successfully authenticated")
            response = Response(
                status=200,
                content=Content(
                    b"application/json",
                    json_settings.dumps(
                        {
                            "access_token": data.access_token,
                            "refresh_token": data.refresh_token,
                        }
                    ).encode("utf-8"),
                ),
            )
        elif status is AUTH_TIMEOUT:
            logger.warning("auth service is timeout")
            response = Response(status=504)
        else:  # forbidden, need login again
            response = Response(status=403)
    elif grpc_status is GRPC_TIMEOUT:
        # uvicorn responds 403 no matter what ws code is only when not accept
        response = Response(status=504)
    else:
        logger.warning(f"failed rpc call, {result.info}")
        response = Response(status=400)  # Bad Request
    return response


# TODO add this logic
def resend_confirmation(request: Request) -> Response:
    pass


async def file_Assistant(request: Request) -> Response:
    pass


async def query_user(request: Request, grpc_manager: GrpcClientManager) -> Response:
    form = await request.form()
    email = form.get("email")
    if email is None:
        return text("Missing required field in the form", status=400)  # Bad Request

    user_service: UserService = grpc_manager.find_service("UserService")
    if user_service is None:
        logger.warning("User Service is unavailable")
        return Response(500)

    result: CallResult = await user_service.UserQuery(email=email, timeout=3)
    if (grpc_status := result.status) is GRPC_SUCCESS:
        data: UserQueryReply = result.data
        if data.success:
            user = data.user
            return json(
                {
                    "seq": user.seq,
                    "uid": UUID(bytes=user.uid, version=1).hex,
                    "username": user.username,
                }
            )
        elif (code := data.code) is USER_DB_TIMEOUT:
            return Response(status=504)
        elif code is USER_NOT_EXISTS:
            return Response(status=404)
        else:
            return Response(status=502)  # unknown error
    elif grpc_status is GRPC_TIMEOUT:
        logger.warning("gateway countered timeout when new friend")
        return Response(status=504)  # gateway timeout
    else:
        info = result.info
        logger.warning(f"\t{info}")
        return json({"info": info}, status=400)  # Bad Request
