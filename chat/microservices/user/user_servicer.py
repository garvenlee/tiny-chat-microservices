from logging import getLogger
from time import monotonic
from typing import cast, Optional

from asyncio import BaseEventLoop, get_running_loop
from grpc.aio import ServicerContext
from werkzeug.security import generate_password_hash, check_password_hash

from chatp.database.model import (
    ExecutionResult,
    DB_SUCCESS,
    DB_TIMEOUT_HANDLING,
    DB_INFO_DUP_ENTRY,
)
from chatp.proto.services.user.user_pb2_grpc import UserServicer as ProtoServicer
from chatp.proto.services.user.user_pb2 import (
    USER_INCORRECT_EMAIL,
    USER_INCORRECT_PWD,
    USER_ALREADY_EXISTS,
    USER_NOT_EXISTS,
    USER_DB_TIMEOUT,
    USER_UNKNOWN_ERROR,
    UserDetailedInfo,
    UserLoginRequest,
    UserLoginReply,
    UserRegisterRequest,
    UserRegisterReply,
    UserRegisterConfirmRequest,
    UserRegisterConfirmReply,
    UserQueryRequest,
    UserQueryReply,
)

from executor import DbExecutor


logger = getLogger("UserServicer")
logger.setLevel(10)


class UserServicer(ProtoServicer):
    def __init__(self, executor: DbExecutor, loop: Optional[BaseEventLoop] = None):
        if loop is None:
            loop = get_running_loop()
        self._run_in_executor = loop.run_in_executor

        # executor.meth implicitly convey `self`<executor instance>
        # self.login_user just reuse executor.login_user, dont convey `self`
        # in this way, reduce one attributes lookup
        self.login_user = executor.login_user
        self.register_user = executor.register_user
        self.query_user = executor.query_user
        self.confirm_user = executor.confirm_user

    async def UserLogin(
        self, request: UserLoginRequest, context: ServicerContext
    ) -> UserLoginReply:
        email, password = request.email, request.password
        result, delay = await self.login_user(
            email=email, timeout=context.time_remaining()
        )
        if result is None:
            return UserLoginReply(success=False, code=USER_DB_TIMEOUT)

        # logger = self.logger
        logger.warning(f"UserLogin query consumes: {delay}")

        result = cast(ExecutionResult, result)
        status = result.status
        if status is DB_SUCCESS:
            if query_result := result.data:
                if query_result["confirmed"]:
                    hash_password = query_result.get("password")
                    checkpoint = monotonic()
                    if await self._run_in_executor(
                        None, check_password_hash, hash_password, password
                    ):
                        logger.warning(
                            f"one pwd check consumes: {monotonic() - checkpoint}"
                        )
                        reply = UserLoginReply(
                            success=True,
                            user=UserDetailedInfo(
                                seq=query_result["seq"],
                                uid=query_result["uid"].bytes,
                                username=query_result["username"],
                            ),
                        )
                    else:
                        logger.info("IncorrectPwd...")
                        reply = UserLoginReply(success=False, code=USER_INCORRECT_PWD)
                else:
                    reply = UserLoginReply(success=False, code=USER_NOT_EXISTS)
            else:
                logger.warning("IncorrectEmail...")
                reply = UserLoginReply(success=False, code=USER_INCORRECT_EMAIL)
        elif status is DB_TIMEOUT_HANDLING:
            logger.warning("timeout when waiting db_service to return a result")
            reply = UserLoginReply(success=False, code=USER_DB_TIMEOUT)
        else:
            logger.info(f"{result.msg}")
            reply = UserLoginReply(success=False, code=USER_UNKNOWN_ERROR)

        if not context.cancelled():
            return reply

    async def UserRegister(
        self, request: UserRegisterRequest, context: ServicerContext
    ) -> UserRegisterReply:
        email, password = request.email, request.password
        hash_password = await self._run_in_executor(
            None, generate_password_hash, password, "pbkdf2:sha256:10000"
        )
        result: Optional[ExecutionResult]
        reply: Optional[UserRegisterReply] = None
        # logger = self.logger
        while not context.cancelled() and reply is None:
            result, delay = await self.register_user(
                email=email,
                password=hash_password,
                username=request.username,
                timeout=context.time_remaining(),
            )
            if result is None:
                # TODO more detiled info about Timeout & Exception
                return UserRegisterReply(success=False, code=USER_DB_TIMEOUT)

            if (status := result.status) is DB_SUCCESS:
                logger.info(f"Registered Successfully! consumes {delay}")
                query_result = result.data
                if query_result["confirmed"]:
                    logger.warning(f"user {email} already exists.")
                    reply = UserRegisterReply(success=False, code=USER_ALREADY_EXISTS)
                else:
                    reply = UserRegisterReply(success=True, seq=query_result["seq"])
            elif status is DB_TIMEOUT_HANDLING:  # almost impossible
                # TODO Corner Check
                # Timeout means client pauses the wait, but dbms may be still in operation.
                # so how to guarantee the consistency?
                # 1.asyncpg can cancel this request, but it's asynchronous
                # 2.SQL expression and logical design ensure the consistency.
                reply = UserRegisterReply(success=False, code=USER_DB_TIMEOUT)
            elif status is DB_INFO_DUP_ENTRY:
                continue
            else:  # failed
                logger.warning(
                    f"db insert failed, maybe db server is down: {result.msg}"
                )
                reply = UserRegisterReply(success=False, code=USER_UNKNOWN_ERROR)

        if not context.cancelled():
            return reply

    async def UserRegisterConfirm(
        self, request: UserRegisterConfirmRequest, context: ServicerContext
    ) -> UserRegisterConfirmReply:
        result, _ = await self.confirm_user(
            seq=request.seq, timeout=context.time_remaining() - 0.5
        )
        if result is None:
            return UserRegisterReply(success=False, code=USER_UNKNOWN_ERROR)

        result = cast(ExecutionResult, result)
        status = result.status
        if status is DB_SUCCESS:
            reply = UserRegisterConfirmReply(success=True)
        elif status is DB_TIMEOUT_HANDLING:  # almost impossible
            reply = UserRegisterConfirmReply(success=False, code=USER_DB_TIMEOUT)
        else:  # failed
            logger.warning(f"db update failed, maybe db server is down: {result.msg}")
            reply = UserRegisterConfirmReply(success=False, code=USER_UNKNOWN_ERROR)

        # if confirm successfully but rpc was cancelled.
        if not context.cancelled():
            return reply

    async def UserQuery(
        self, request: UserQueryRequest, context: ServicerContext
    ) -> UserQueryReply:
        result, _ = await self.query_user(
            email=request.email, timeout=context.time_remaining()
        )
        if result is None:
            return UserQueryReply(success=False, code=USER_UNKNOWN_ERROR)

        result = cast(ExecutionResult, result)
        status = result.status
        if status is DB_SUCCESS:
            data = result.data  # None or Record
            if data is not None and data["confirmed"]:
                # asyncpg auto-converts data type according to db defination
                reply = UserQueryReply(
                    success=True,
                    user=UserDetailedInfo(
                        seq=data["seq"],
                        uid=data["uid"].bytes,
                        username=data["username"],
                    ),
                )
            else:  # not exists
                reply = UserQueryReply(success=False, code=USER_NOT_EXISTS)
        elif status is DB_TIMEOUT_HANDLING:
            logger.info("timeout when waiting db_service to return a result")
            reply = UserQueryReply(success=False, code=USER_DB_TIMEOUT)
        else:
            logger.info(f"{result.msg}")
            reply = UserQueryReply(success=False, code=USER_UNKNOWN_ERROR)

        if not context.cancelled():
            return reply
