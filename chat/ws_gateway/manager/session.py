from logging import getLogger
from base64 import b64encode
from secrets import token_bytes  as secrets_token_bytes
from time import mktime as time_mktime
from datetime import datetime
from collections import OrderedDict
from itertools import count, cycle
from typing import Optional, AsyncIterable, Callable
from contextlib import suppress, asynccontextmanager

from asyncio import (
    wait_for,
    get_running_loop,
    Future,
    TimerHandle,
    Queue,
    BaseEventLoop,
    TimeoutError as AsyncIOTimeoutError,
    CancelledError,
)
from aiolimiter import AsyncLimiter
from websockets.exceptions import ConnectionClosed
from google.protobuf.message import Message as ProtobufMessage

# from memory_profiler import profile
from starlette.websockets import WebSocket, WebSocketDisconnect
from starlette.requests import Headers
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    WS_1000_NORMAL_CLOSURE,
    WS_1011_INTERNAL_ERROR,
    WS_1013_TRY_AGAIN_LATER,
)

from chatp.manager.grpc_client import GrpcClientManager
from chatp.multiprocess.worker import WorkerProcess
from chatp.rpc.model import *
from chatp.redis.client import RedisClient
from chatp.redis.model import *
from chatp.proto.services.user.user_pb2 import (
    UserDeviceType,
    TERMINAL,
    PC,
    WEB,
    ANDROID,
    IOS,
)
from chatp.proto.services.push.push_pb2 import (
    MessageLog,
    PubEventType,
    PubEventToUser,
    PubEventFromUser,
    PubEventAckFromUser,
    ACK_USER_MESSAGE,
)
from chatp.proto.services.transfer.msg_data_pb2 import ClientMsgData
from chatp.proto.services.auth.auth_user_pb2 import (
    AUTH_SUCCESS,
    AUTH_TIMEOUT,
    AUTH_EXPIRED,
    AuthTokenReply,
)

from rpc.auth_service import AuthService
from rpc.transfer_service import UpstreamTransferService
from rpc.proto.ws_pb2 import StatusFrame
from utils.exceptions import InvalidRateException
from utils.model import *

logger = getLogger("websocket-session")
logger.setLevel(10)

datetime_utcnow = datetime.utcnow
datetime_timestamp = datetime.timestamp


def get_clock():
    now = datetime_utcnow()
    return int(time_mktime(now.timetuple()) * 1000 + now.microsecond / 1000)  # ms


def get_timestamp():
    return int(datetime_utcnow().timestamp() * 1000)  # ms


class ReceiverRateLimiter:
    FAULT_TOLERANCE = 3

    __slots__ = (
        "_loop_call_later",
        "_current_fault_tolerance",
        "_limiter",
        "_refresh_timer_handler",
    )

    def __init__(self, loop: Optional[BaseEventLoop] = None):
        if loop is None:
            loop: BaseEventLoop = get_running_loop()
        self._loop_call_later = loop.call_later

        self._current_fault_tolerance = ReceiverRateLimiter.FAULT_TOLERANCE
        self._limiter = AsyncLimiter(max_rate=2, time_period=1)  # 2 message per second

        self._refresh_timer_handler: TimerHandle | None = None

    def refresh(self):
        self._current_fault_tolerance = ReceiverRateLimiter.FAULT_TOLERANCE

    async def check_before_receive_message(self):
        try:
            await wait_for(self._limiter.acquire(), 1)  # need to check the time
        except AsyncIOTimeoutError:
            if self._current_fault_tolerance:  # maybe network dalay
                self._current_fault_tolerance -= 1

                if (handler := self._refresh_timer_handler) is not None:
                    handler.cancel()
                self._refresh_timer_handler = self._loop_call_later(10, self.refresh)
            else:
                self._refresh_timer_handler.cancel()
                raise InvalidRateException

    def clear(self):
        if (handler := self._refresh_timer_handler) is not None:
            handler.cancel()


# each user has a limiter_check? maybe consumes too much memory
class FrameReceiver(AsyncIterable):
    __slots__ = "websocket", "limiter_check"

    def __init__(self, websocket: WebSocket, limiter: ReceiverRateLimiter):
        self.websocket = websocket
        self.limiter_check = limiter.check_before_receive_message

    def __aiter__(self):
        return self

    async def __anext__(self) -> ProtobufMessage:
        await self.limiter_check()  # may raise InvalidRateException
        return await self.build_frame()

    async def build_frame(self) -> ProtobufMessage:
        websocket = self.websocket
        recv_bytes = websocket.receive_bytes
        data = await recv_bytes()
        return PubEventFromUser.FromString(data)


class FrameGenerator(AsyncIterable):
    __slots__ = "_queue"

    def __init__(self, queue: Queue[ProtobufMessage]):
        self._queue = queue

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.get_frame()

    async def get_frame(self):
        data = await self._queue.get()
        return data.SerializeToString()


class UserCache:
    __slots__ = "_cache"

    def __init__(self):
        self._cache: dict[int, int] = {}

    def set(self, key_id: int, cache_value: int):
        cache = self._cache
        if (old_value := cache.get(key_id)) is None:
            cache[key_id] = cache_value
        else:  # use the old one
            if cache_value < old_value:
                logger.warning(
                    "Found duplicate message with time confusion, keep the former one now"
                )
            else:
                logger.warning("Found duplicate message, just kepp the former one")
            cache_value = old_value
            # cache[key_id] = cache_value
        return cache_value

    def get(self, key_id: int):
        return self._cache.get(key_id)


class WebsocketSession:
    __slots__ = (
        "wsid",
        "websocket",
        "session_key",
        "device_tp",
        "appid",
        "write_queue",
        "last_online_time",
        "last_offline_time",
        "user_cache",
        "state",
    )

    def __init__(
        self,
        websocket: WebSocket,
        wsid: str,
        session_key: int,
        device_tp: UserDeviceType,
        appid: str,
    ):
        self.wsid = wsid
        self.websocket = websocket
        self.session_key = session_key
        self.device_tp = device_tp
        self.appid = appid

        self.last_online_time = get_timestamp()
        self.write_queue: Queue = Queue(maxsize=1024)  # PubData

        self.user_cache: dict[int, int] = {}
        self.state = SESSION_IDLE

    @property
    def active(self):
        return self.state & SESSION_CLOSING == 0

    def rebind(
        self,
        websocket: WebSocket,
        session_key: int,
        device_tp: UserDeviceType,
        appid: str,
    ):
        self.websocket = websocket
        self.session_key = session_key
        self.device_tp = device_tp
        self.appid = appid

        self.last_online_time = get_timestamp()

    def clear(self):
        # designed to reuse wsid
        self.websocket = self.device_tp = self.session_key = self.appid = None
        self.user_cache.clear()
        self.last_offline_time = get_timestamp()
        self.state = SESSION_IDLE

    def serialize(self):
        pass

    def deserialize(self):
        pass

    @staticmethod
    async def before_handshake(
        websocket: WebSocket, headers: Headers, appid_prefix: str
    ):
        try:
            uid = int(headers["seq"])  # must contains uid field
            user_device = headers["platform"].upper()
            auth_field: str = headers["Authorization"]
            appid: str = headers["appid"]
        except (KeyError, ValueError) as exc:
            logger.warning(f"Invalid Headers: {exc}")
            # 403 Forbidden, client must login again
            await websocket.close(code=HTTP_400_BAD_REQUEST, reason="Invalid Headers")
            return
        else:
            if user_device not in SessionManager.DEVICE_MAPPING:
                logger.warning(f"Unknown DeviceType: {user_device}")
                await websocket.close(
                    code=HTTP_400_BAD_REQUEST, reason=f"Invalid Platform: {user_device}"
                )
                return

            if not auth_field.startswith("Bearer "):
                logger.warning(f"Invalid `Authorization`: {auth_field}")
                # 403 Forbidden
                await websocket.close(
                    code=HTTP_400_BAD_REQUEST,
                    reason="Invalid `Authorization` in headers",
                )
                return

            if not appid.startswith(appid_prefix):
                logger.warning(f"Invalid `appid`: {appid}")
                await websocket.close(
                    code=HTTP_400_BAD_REQUEST,
                    reason="Invalid `appid` in headers",
                )

        return uid, user_device, auth_field, appid

    @staticmethod
    async def websocket_upgrade(
        websocket: WebSocket,
        grpc_manager: GrpcClientManager,
        auth_field: bytes,
    ) -> bool:
        access_token = str(auth_field[7:])
        auth_service: AuthService = grpc_manager.find_service("AuthService")
        result: CallResult = await auth_service.AuthToken(access_token=access_token)
        # TODO auth service unavailable
        if (grpc_status := result.status) is GRPC_SUCCESS:
            data: AuthTokenReply = result.data
            if (status := data.status) is AUTH_SUCCESS:
                # logger.info("user successfully authenticated")
                await websocket.accept("chatp")
                return True
            elif status is AUTH_EXPIRED:
                # logger.warning("user's token is expired, needs refresh")
                await websocket.accept("chatp")
                # need refresh
                await websocket.close(
                    code=WS_4001_REFRESH_REQUIRED, reason="your token needs refresh"
                )
                return False
            elif status is AUTH_TIMEOUT:
                logger.warning("user service timeout")
                await websocket.accept("chatp")
                await websocket.close(
                    code=WS_1013_TRY_AGAIN_LATER,
                    reason="user service is busy, maybe try later",
                )
                return False
            else:  # failed, client must login again
                await websocket.close(
                    code=403,
                    reason="invalid user authenticate",
                )
                return False
        elif grpc_status is GRPC_TIMEOUT:
            # uvicorn responds 403 no matter what ws code is when handshake failed
            logger.warning("auth service is timeout")
            await websocket.accept("chatp")
            await websocket.close(
                code=WS_1013_TRY_AGAIN_LATER,
                reason="busy now, maybe try later",
            )
            return False
        else:
            logger.warning(f"RPC Call failed: {result.info}")
            # 403 Forbidden
            await websocket.close(code=403, reason="Unknown Error")  # needs relogin
            return False

    async def negotiate_kick_off(self, websocket: WebSocket):
        try:
            await websocket.send_bytes(
                StatusFrame(
                    kicked_off=True, extra=bytes(self.wsid, "ascii")
                ).SerializeToString()
            )  # websocket.send may raise ConnectionClosed
            confirmation: bytes = await wait_for(
                websocket.receive_bytes(),
                timeout=5,
            )  # websocket.recv found ConnectionClosed, which was converted to WebSocketDisconnect
        except AsyncIOTimeoutError:
            with suppress(ConnectionClosed):
                await websocket.close(
                    WS_4003_NEGOTIATE_TIMEOUT,
                    reason="Client Timeout in `negotiate_kick_off`.",
                )
            return False
        except ConnectionClosed:
            return False
        except WebSocketDisconnect as exc:
            if exc.code == WS_1012_SERVICE_RESTART:
                logger.warning("WsGateway was already shutdown")
            else:
                logger.exception("WsConnection is lost: %s", exc, exc_info=exc)
            return False
        except BaseException as exc:
            logger.exception(
                "Found unknown exception in `negotiate_kick_off`: %s", exc, exc_info=exc
            )
            return False
        else:
            if confirmation == b"1":
                return True
            else:
                with suppress(ConnectionClosed):
                    await websocket.close(
                        WS_1000_NORMAL_CLOSURE,
                        reason="Negotiate to keep the former connection.",
                    )
                return False

    async def check_multi_devices(
        self,
        websocket: WebSocket,
        redis_service: RedisClient,
        addr_key: str,
        addr_field: str,
    ):
        result, status = await redis_service.redis_hget(
            key=addr_key, field=addr_field, timeout=5
        )

        if status is REDIS_SUCCESS:
            if result:
                return await self.negotiate_kick_off(websocket)  # True or False
            else:  # No other device
                return
        elif status is REDIS_TIMEOUT:
            logger.warning("Found exc when UserMultiTerminalCheck: Grpc-call Timeout.")
        else:
            logger.error("Found exc when UserMultiTerminalCheck: Unknown Error.")

        with suppress(ConnectionClosed):
            await websocket.close(WS_1013_TRY_AGAIN_LATER)
        return False  # RedisFailed

    async def activate(
        self, redis_service: RedisClient, addr_key: str, addr_field: str
    ) -> bool:
        # online_time = get_timestamp()  # maybe used

        _, status = await redis_service.redis_hset(
            key=addr_key,  # maybe multi-terminal
            field=addr_field,
            value=SessionManager.GATEWAY_ADDR,
            timeout=5,
        )
        if status is REDIS_SUCCESS:
            ## hset return the added num
            return True
        elif status is REDIS_TIMEOUT:
            logger.warning("RedisClient<HSet> timeout.")
            with suppress(ConnectionClosed):
                await self.websocket.close(
                    WS_1013_TRY_AGAIN_LATER,
                    reason="Found exc when setting online status: Grpc-Call Timeout",
                )
        else:
            logger.warning("RedisClient<HSet> failed.")
            with suppress(ConnectionClosed):
                await self.websocket.close(
                    WS_1011_INTERNAL_ERROR,
                    reason="Found exc when setting online status: Unknown Error",
                )
        return False

    async def deactivate(
        self, redis_service: RedisClient, addr_key: str, addr_field: str
    ) -> bool:
        # TODO make sure this coroutine complete successfully / if failed, inconsistency
        # currently implementation: each grpc service with three backoff-retry
        result, status = await redis_service.redis_hdel(addr_key, addr_field, timeout=5)
        if status is REDIS_SUCCESS:
            logger.warning(f"Found {result} when redis_hdel")
            return True
        elif status is REDIS_TIMEOUT:
            logger.warning("Found exc when UserOffline: Timeout")
        else:
            logger.warning("Found exc when UserOffline: Unknown Error")

        get_running_loop().create_task(
            redis_service.redis_hdel(addr_key, addr_field, timeout=30)
        )
        logger.warning(f"Needs to clear RedisOnlineStatus: {addr_key} / {addr_field}.")
        return False  # means failed

    async def read_messages(
        self,
        channel_queue: Queue,  # ack to PushRpc
        transfer_service_getter: Callable[[None], UpstreamTransferService],
    ):
        async def on_user_push_message(message_queue: Queue):
            nonlocal inflight_id, max_sent_id
            while True:
                inflight_id = 0
                item: ClientMsgData = await message_queue.get()
                msg_data, delivery_id = item.data, item.delivery_id

                service: UpstreamTransferService = transfer_service_getter(
                    hash_key=str(msg_data.session_id)
                )
                if service is None:
                    # TODO needs to shield?
                    logger.warning("TransferService is unavailable temporarily")
                # ------------------------------------------------------------------------
                # 1.grpc call is timeout, and message_id is 0
                # 2.grpc_call is successful, and ack is inflight, but the front already determine
                #   it timeout
                #
                # About 1, message maybe already published to RMQStream Queue, and when
                #   user retries to send again, GRPC Method `DeliverMessage` will return fast
                #   as long as it is routed to the same server, but it's likely to exist duplicate
                #   messages with different msg_id but same delivery_id though. In this case, the
                #   single superstream consumer must make sure the message idempotency.
                # About 2, the front code handles it when user retries to send
                # ------------------------------------------------------------------------
                inflight_id = delivery_id
                message_id = await service.deliver_message(item, timeout=5)

                if message_id:
                    if delivery_id > max_sent_id:
                        max_sent_id = delivery_id
                    logger.info("PushMessageAck is ready to return back to the front")
                    write_queue_put(
                        PubEventToUser(
                            log=MessageLog(
                                evt_tp=ACK_USER_MESSAGE,
                                channel_number=0,
                                delivery_id=delivery_id,
                            ),
                            evt_data=message_id.to_bytes(8),
                        )
                    )

        # TODO when online, user pull offline message, max local_id
        # TODO pull history messages <- client hold the seq list?
        self.state = SESSION_ACTIVE  # here, session can read/write TODO CORNER CHECK
        limiter = ReceiverRateLimiter()

        write_queue_put = self.write_queue.put_nowait
        channel_queue_put = channel_queue.put_nowait

        pending_deliver = Queue()
        pending_deliver_put = pending_deliver.put_nowait
        deliver_task = get_running_loop().create_task(
            on_user_push_message(pending_deliver)
        )

        inflight_id = max_sent_id = 0
        # shield_event = AsyncIOEvent()
        try:
            async for frame in FrameReceiver(self.websocket, limiter):
                match frame.evt_tp:
                    case PubEventType.PUSH_USER_MESSAGE:  # deliver
                        logger.debug("received one user message, needs to publish")
                        pending_deliver_put(ClientMsgData.FromString(frame.payload))
                    case PubEventType.ACK_ACTION:  # ack_to_rpc
                        channel_queue_put(PubEventAckFromUser.FromString(frame.payload))
                    case _:
                        pass
        finally:
            deliver_task.cancel()
            limiter.clear()

    async def write_messages(self, session_key: int):
        queue = self.write_queue
        websocket_send_bytes = self.websocket.send_bytes
        try:
            async for frame in FrameGenerator(queue):
                await websocket_send_bytes(frame)
        except CancelledError:
            logger.info(f"User {session_key}'s Writer Task is Cancelled")
        finally:
            # exhausted queue_item
            while queue.qsize():
                queue.get_nowait()


class SessionManager:
    # __get_sizeof__ = sys.getsizeof
    __get_sizeof__ = len
    __idle_capacity__ = 1024  # max-connections in 1G is 1000, ws buffer is 1MB
    __idle_threshold__ = 60 * 1000  # 60s

    __slots__ = (
        "_seq_count",
        "_sessions",
        "_idle_sessions",
        "_idle_capacity",
        "_waiters",
        "shutdown",
        "id_generator",
        "channel_queue",
        "transfer_service_getter",
    )

    PROC: WorkerProcess = None
    PLATFORM_ID: str = None
    GATEWAY_ADDR: str = None

    DEVICE_MAPPING: dict[str, int] = None
    DEVICE_KINDS_NUM: int = None

    APPID_PREFIX: str = None

    def __init__(self):
        self._seq_count = count()

        self._sessions: dict[int, WebsocketSession] = {}
        self._idle_sessions: OrderedDict[int, WebsocketSession] = OrderedDict()

        self._waiters: dict[int, Future] = {}
        self.shutdown = False

        self.id_generator = cycle(range(2**31 - 1))

        self.channel_queue: Queue
        self.transfer_service_getter: Callable[[str], UpstreamTransferService]

    def bind_queue(self, queue: Queue):
        self.channel_queue = queue

    def bind_service_getter(
        self, transfer_service_getter: Callable[[str], UpstreamTransferService]
    ):
        self.transfer_service_getter = transfer_service_getter

    def recycle_session(self, session_key: int):
        if session := self._sessions.pop(session_key, None):
            session.clear()  # IDLE

            idle_sessions = self._idle_sessions
            if (
                SessionManager.__get_sizeof__(idle_sessions)
                < SessionManager.__idle_capacity__
            ):
                idle_sessions[session_key] = session

            if (
                waiter := self._waiters.get(session_key)
            ) is not None and not waiter.done():
                waiter.set_result(None)

    async def wait_for_recycle(self, session_key: int, timeout: int = 3) -> bool:
        if session_key in self._sessions:
            waiters = self._waiters
            waiters[session_key] = waiter = Future()
            try:
                await wait_for(waiter, timeout=timeout)
            except AsyncIOTimeoutError:
                return False
            else:
                return True
            finally:
                waiters.pop(session_key, None)

    def get(self, session_key: int):
        return self._sessions.get(session_key)

    def reuse_session(self, session_key: int):
        session = self._idle_sessions.pop(session_key, None)
        if session is not None:
            self._sessions[session_key] = session
            return session

    def retrieve_session(self, session_key: int):
        session = self._sessions.pop(session_key, None)
        if session is not None:
            self._idle_sessions[session_key] = session

    @classmethod
    def bind(
        cls, proc: WorkerProcess, platform_id: str, gateway_addr: str, appid_prefix: str
    ):
        cls.PROC = proc
        cls.PLATFORM_ID = platform_id
        cls.GATEWAY_ADDR = gateway_addr

        cls.DEVICE_MAPPING = {
            "TERMINAL": TERMINAL,
            "WEB": WEB,
            "PC": PC,
            "ANDROID": ANDROID,
            "IOS": IOS,
        }
        cls.DEVICE_KINDS_NUM = 5

        cls.APPID_PREFIX = appid_prefix

    @staticmethod
    @asynccontextmanager
    async def lock_session(
        session_lock_key: int, redis_client: RedisClient
    ) -> Optional[bool]:
        success, _ = await redis_client.redis_setnx(session_lock_key, 1, timeout=2)
        try:
            yield success
        except ConnectionClosed as exc:
            logger.error("Found ConnectionClosed: %s", exc, exc_info=exc)
        finally:
            if success:
                _, status = await redis_client.redis_delete(session_lock_key)
                if status is not REDIS_SUCCESS:  # just retry once
                    get_running_loop().create_task(
                        redis_client.redis_delete(session_lock_key)
                    )

    # @profile
    def create_session(
        self, ws: WebSocket, session_key: int, device_tp: UserDeviceType, appid: str
    ):
        sessions = self._sessions
        platform_id = SessionManager.PLATFORM_ID
        if idle_sessions := self._idle_sessions:  # IDLE
            if (session := idle_sessions.get(session_key)) is not None:
                del idle_sessions[session_key]
            else:
                # FIFO: young session may be reused later by the exactly user
                #       use the oldest item may be helpful for memory manager
                _, session = idle_sessions.popitem(last=False)
                # session.uid = uid  # uid maybe unnecessary

            # maybe reuse the wsid
            if session.wsid[: len(platform_id)] != platform_id:
                session.wsid = f"{platform_id}-{self.session_id()}"
            session.rebind(ws, session_key, device_tp, appid)

            sessions[session_key] = session
            return session

        wsid = f"{platform_id}-{self.session_id()}"  # 47B
        session = WebsocketSession(ws, wsid, session_key, device_tp, appid)  # IDLE
        sessions[session_key] = session
        return session

    def session_id(self) -> str:
        """Generate a unique session id."""
        mask = 0xFFFFFFFF
        id = b64encode(
            secrets_token_bytes(8)
            + (get_clock() & mask).to_bytes(4, "big")
            + (next(self._seq_count) & mask).to_bytes(4, "big")
        )  # 24B
        return id.decode("utf-8").replace("/", "_").replace("+", "-")
