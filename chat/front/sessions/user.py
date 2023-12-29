from uuid import UUID
from logging import getLogger
from enum import IntEnum
from contextlib import suppress
from collections import deque
from operator import attrgetter
from typing import Union, Optional, AsyncGenerator, Callable, Iterable, Any
from random import randint

from asyncio import (
    Future,
    Task,
    Queue,
    TimeoutError as AsyncIOTimeoutError,
    CancelledError,
    BaseEventLoop,
    wait_for,
    sleep,
)
from blacksheep.settings.json import json_settings
from aiomisc import asyncbackoff
from httpx import TimeoutException, Response as HttpxResponse
from google.protobuf.message import Message as ProtobufMessage
from websockets.exceptions import ConnectionClosed
from websockets.client import WebSocketClientProtocol

from sortedcontainers import SortedList

from network.http import (
    HttpConnection,
    HttpStatus,
    DummyResponse,
    status_map,
    SUCCESS,
    FAILED,
    TIMEOUT,
)
from network.ws import WsConnection
from base.chat import BaseChatHandler
from sessions.chat import ChatSession
from rpc.ws_pb2 import StatusFrame
from models.user import User
from models.friend import (
    Friend,
    RelationState,
    FriendRequestData,
    FriendConfirmData,
    ACCEPT_INBOUND,
    REJECT_INBOUND,
    IGNORE_INBOUND,
)
from models.websocket import *
from utils.context import platform, appid
from utils.backoff import EqualJitterBackoff
from utils.exceptions import Rejected, Unavailable

from chatp.proto.services.push.push_pb2 import (
    MessageLog,
    PubEventType,
    PubEventToUser,
    PubEventFromUser,
    PubEventAckFromUser,
    PUSH_FRIEND_REQUEST,
    PUSH_FRIEND_CONFIRM,
    # PUSH_FRIEND_SESSION,
    PUSH_USER_MESSAGE,
    ACK_ACTION,
    ACK_FRIEND_REQUEST,
    ACK_FRIEND_CONFIRM,
    # ACK_FRIEND_SESSION,
    ACK_USER_MESSAGE,
)
from chatp.proto.services.friend.friend_pb2 import (
    FriendRequest,
    FriendConfirm,
    # FriendSession,
    ACCEPTED,
    IGNORED,
)
from chatp.proto.services.transfer.msg_data_pb2 import (
    MsgData,
    ClientMsgData,
    ServerMsgData,
)
from chatp.message.stream import MessageStream, OutboundMessageLog

logger = getLogger("UserSession")
logger.setLevel(10)


class SessionState(IntEnum):
    VALID = 0
    EXPIRED = 1


wscode_mapping = {
    WS_1011_INTERNAL_ERROR: INTERNAL_ERROR,  # server internal error
    WS_1012_SERVICE_RESTART: INTERNAL_ERROR,  # maybe os killed process
    WS_1013_TRY_AGAIN_LATER: RETRY_LATER,  # try later
    WS_4001_REFRESH_REQUIRED: REFRESH_REQUIRED,  # special code, needs refresh
    WS_4003_NEGOTIATE_TIMEOUT: NEGOTIATE_TIMEOUT,  # negotiate timeout
    WS_4008_CONNECT_CONFLICT: LOGIN_CONFLICT,  # login conflict
}


class HttpHandlerMixin:
    # __slots__ = ("_user", "http", "token_state")

    def __init__(self, http: HttpConnection):
        self._user: Optional[User] = None

        self.http = http
        self.token_state = SessionState.VALID

    @property
    def is_active(self):
        return self.token_state is SessionState.VALID

    @property
    def user(self):
        if self._user is None:
            raise RuntimeError("Not logged in yet")
        return self._user

    @property
    def user_seq(self) -> int:
        if self._user is None:
            raise RuntimeError("Not logged in yet")
        return self._user.seq

    @property
    def user_id(self) -> str:
        if self._user is None:
            raise RuntimeError("Not logged in yet")
        return self._user.uid

    @property
    def username(self) -> str:
        if self._user is None:
            raise RuntimeError("Not logged in yet")
        return self._user.username

    @property
    def access_token(self) -> str:
        if self._user is None:
            raise RuntimeError("Not logged in yet")
        return self._user.access_token

    @access_token.setter
    def access_token(self, token: str):
        if self._user is None:
            raise RuntimeError("Not logged in yet")
        self._user.access_token = token

    @property
    def refresh_token(self) -> str:
        if self._user is None:
            raise RuntimeError("Not logged in yet")
        return self._user.refresh_token

    @refresh_token.setter
    def refresh_token(self, token: str):
        if self._user is None:
            raise RuntimeError("Not logged in yet")
        self._user.refresh_token = token

    async def login(self, email: str, password: str) -> HttpStatus:
        resp = await self.http.login(email, password)
        status = status_map.get(resp.status_code, FAILED)
        if status is SUCCESS:
            data = resp.json()
            seq = data.get("seq")
            uid = data.get("uid")
            username = data.get("username")
            if seq is None or uid is None or username is None:
                return FAILED

            headers = resp.headers
            access_token = headers.get("access_token")
            refresh_token = headers.get("refresh_token")
            if access_token is None or refresh_token is None:
                return FAILED

            self._user = User(seq, uid, username, email, access_token, refresh_token)
        return status

    async def register(self, email: str, password: str, username: str) -> HttpStatus:
        resp = await self.http.register(email, password, username)
        return status_map.get(resp.status_code, FAILED)

    @asyncbackoff(
        attempt_timeout=None,
        deadline=None,
        max_tries=5,
        pause=randint(60 * 5, 60 * 10),
        exceptions=(TimeoutException,),
    )
    async def refresh(self):
        resp = await self.http.refresh(self.user_id, self.refresh_token)
        status = status_map.get(resp.status_code, FAILED)
        if status is SUCCESS:
            json_body = resp.json()
            self.access_token = json_body["access_token"]
            self.refresh_token = json_body["refresh_token"]
        elif status is TIMEOUT:
            raise TimeoutException("service timeout")
        else:
            self.token_state = SessionState.EXPIRED
            raise Rejected()

    async def query_user(self, email: str) -> tuple[Optional[User], HttpStatus]:
        resp = await self.http.query_user(email, self.access_token)
        status = status_map.get(resp.status_code, FAILED)

        user = None
        if status is SUCCESS:
            data = resp.json()
            seq = data.get("seq")
            uid = data.get("uid")
            username = data.get("username")
            if seq is None or uid is None or username is None:
                status = FAILED
            user = User(seq, uid, username, email)

        return user, status

    async def add_friend(
        self, address_id: int, request_message: Optional[str]
    ) -> HttpStatus:
        user = self._user
        resp = await self.http.add_friend(
            address_id,
            user.uid,
            user.email,
            user.username,
            self.access_token,
            request_message,
        )
        return status_map.get(resp.status_code, FAILED)

    async def confirm_friend(self, uid: int) -> tuple[Optional[int], HttpStatus]:
        resp = await self.http.confirm_friend(uid, self.access_token)
        status = status_map.get(resp.status_code, FAILED)
        if status is SUCCESS:
            session_id = int(resp.json()["session_id"])
        else:
            session_id = None
        return session_id, status

    async def reject_friend(self, uid: int) -> HttpStatus:
        resp = await self.http.reject_friend(uid, self.access_token)
        return status_map.get(resp.status_code, FAILED)

    @asyncbackoff(
        attempt_timeout=None,
        deadline=None,
        max_tries=3,
        pause=1.5,
        exceptions=(TimeoutException,),
    )
    async def pull_inbox(self, last_max_msg_id: int) -> list[dict]:
        resp = await self.http.pull_inbox(last_max_msg_id, self.access_token)
        status = status_map.get(resp.status_code, FAILED)
        if status is not SUCCESS:
            raise TimeoutException("Server is busy")

        return resp.json()["data"]

    async def pull_sessions(self, friend_ids: list[int], session_ids: list[int]):
        iter_seq = 0
        async for chunk in self.http.pull_sessions(session_ids, self.access_token):
            json_data = json_settings.loads(chunk.decode("ascii"))
            self.collect_lastest_session(friend_ids[iter_seq], json_data["data"])
            iter_seq += 1

    @asyncbackoff(
        attempt_timeout=None,
        deadline=None,
        max_tries=3,
        pause=0.5,
        exceptions=(TimeoutException,),
    )
    async def scratch_friend_list(self):
        resp: Union[HttpxResponse, DummyResponse] = await self.http.get_friend_list(
            self.access_token
        )
        status = status_map.get(resp.status_code, FAILED)
        if status is not SUCCESS:
            raise TimeoutException("Server is busy")

        return self.collect_friend_list(resp.json())

    async def get_chat_list(self) -> None:
        resp: Union[DummyResponse, HttpxResponse] = await self.http.get_chat_list()
        if (status_code := resp.status_code) == 200:
            self.collect_chat_list(resp.json())
        else:
            self.raise_exception(status_code)

    def collect_lastest_session(self, data: bytes) -> None:
        raise NotImplementedError

    def collect_chat_list(self, data: dict) -> None:
        raise NotImplementedError

    def collect_friend_list(self, data: dict) -> dict[int, Friend]:
        raise NotImplementedError

    def raise_exception(self, status_code: int) -> None:
        raise NotImplementedError


class WebsocketConnectionMixin:
    __slots__ = (
        "ws",
        "wsid",
        "wait_connected",
        "can_reconnect",
        "connected_waiter",
        "pending_reconnect_waiter",
    )

    def __init__(self, ws: WsConnection):
        self.ws = ws
        self.wsid: Optional[str] = None

        self.wait_connected = False
        self.can_reconnect = False

        self.connected_waiter = Future()
        self.pending_reconnect_waiter = Future()

    async def maybe_negotiate_kicked_off(
        self, protocol: WebSocketClientProtocol, *, timeout: int
    ) -> WsLoginCode:
        try:
            data = await wait_for(protocol.recv(), timeout)  # negotiate kicked off
            status_frame = StatusFrame.FromString(data)
        except ConnectionClosed as exc:
            # ConnectionClosedOk or ConnectionClosedError
            return wscode_mapping.get(exc.code, INTERNAL_ERROR)
        else:
            if not status_frame.kicked_off:
                login_state = CONNECTED
                self.wsid = status_frame.extra
            else:
                # TODO UI interaction (maybe timeout 60s)
                try:
                    await protocol.send(b"1")  # means kicked
                    _ = await wait_for(protocol.recv(), 5)
                except ConnectionClosed as exc:  # redis or push timeout
                    logger.debug("ConnectionClosed in logical negotiation.")
                    login_state = RETRY_LATER
                except AsyncIOTimeoutError:
                    logger.debug("timeout when wait kicked off confirmation.")
                    login_state = RETRY_LATER
                else:  # confirm_byte == b"1"
                    login_state = CONNECTED
                    self.wsid = status_frame.extra

            return login_state

    async def ws_connect_helper(
        self, user_seq: int, access_token: str
    ) -> AsyncGenerator[WebSocketClientProtocol, Any]:
        aiterator = self.ws.ws_connect(
            headers={
                "seq": user_seq,
                "platform": platform,
                "appid": appid,
                "Authorization": f"Bearer {access_token}",
            },
        )
        try:
            async for protocol in aiterator:  # 3s open_timeout but will retry if failed?
                try:
                    login_state = await self.maybe_negotiate_kicked_off(
                        protocol, timeout=5
                    )
                except (AsyncIOTimeoutError, CancelledError):
                    raise
                except Exception as exc:  # corner case
                    logger.exception("Found exc in StatusFrame: ", exc, exc_info=exc)
                    login_state = UNKNOW_ERROR

                if self.wait_connected and not (waiter := self.connected_waiter).done():
                    waiter.set_result(login_state)
                    if login_state is CONNECTED:
                        yield protocol
                else:  # user code already founds timeout
                    # attempt to reuse WsConnect
                    # Found exc in ws handshake or negotiation, s.t. AsyncIOTimeoutError
                    await self.wait_to_reconnect()
                    if login_state is CONNECTED and protocol.open:
                        self.connected_waiter.set_result(CONNECTED)
                        yield protocol

        except Rejected:  # must spawn a new `ws_connect` coroutine
            if self.wait_connected and not (waiter := self.connected_waiter).done():
                waiter.set_result(REJECTED)
        except Unavailable:  # must spawn a new `ws_connect` coroutine
            if self.wait_connected and not (waiter := self.connected_waiter).done():
                waiter.set_result(SERVER_DOWN)
        except CancelledError:
            # await aiterator.aclose()
            return
        except AsyncIOTimeoutError as exc:
            logger.exception("Found timeout in ws_connect: %s", exc, exc_info=exc)
            if self.wait_connected and not (waiter := self.connected_waiter).done():
                waiter.set_result(NEGOTIATE_TIMEOUT)
        except Exception as exc:  # corner case
            logger.exception("Found exc in ws_connect: %s", exc, exc_info=exc)
            if self.wait_connected and not (waiter := self.connected_waiter).done():
                waiter.set_result(UNKNOW_ERROR)

    async def wait_to_reconnect(self):
        try:
            self.can_reconnect = True
            waiter = self.pending_reconnect_waiter
            await waiter
        finally:
            self.can_reconnect = False
            self.pending_reconnect_waiter = Future()

    def ready_to_reconnect(self):
        self.pending_reconnect_waiter.set_result(None)

    async def wait_for_ws_connected(self, timeout: Union[float, int] = 8):
        try:
            self.wait_connected = True
            waiter = self.connected_waiter
            return await wait_for(waiter, timeout=timeout)
        except AsyncIOTimeoutError:
            return LOGIN_TIMEOUT
        finally:
            self.wait_connected = False
            self.connected_waiter = Future()


class UserSession(HttpHandlerMixin, WebsocketConnectionMixin, BaseChatHandler):
    __slots__ = (
        "_loop",
        "_backoff",
        "_async_tasks",
        "_reader_task",
        "_writer_task",
        "_writer_channel",
        "_handlers",
        "_registered_callbacks",
        "local_id_to_session",
        "min_local_id",
        "max_local_id",
        "last_max_msg_id",
        "message_stream",
        "timeout_logs",
        "chat_sessions",
        "friends",
        "friend_list",
        "timeline",
        "pending_friend_requests",
        "pending_friend_confirms",
    )

    def __init__(self, http: HttpConnection, ws: WsConnection, *, loop: BaseEventLoop):
        super().__init__(http)
        super(HttpHandlerMixin, self).__init__(ws)

        self._loop = loop
        self._backoff = EqualJitterBackoff(cap=10, base=2)

        # channel in ws handle
        self._async_tasks: set[Task] = set()
        self._reader_task: Optional[Task] = None
        self._writer_task: Optional[Task] = None
        self._writer_channel: Queue[ProtobufMessage] = Queue()

        self._handlers: dict[
            PubEventType,
            tuple[Callable[[PubEventToUser], None], Optional[PubEventType]],
        ] = {
            PUSH_FRIEND_REQUEST: (self.on_push_friend_request, ACK_FRIEND_REQUEST),
            PUSH_FRIEND_CONFIRM: (self.on_push_friend_confirm, ACK_FRIEND_CONFIRM),
            # PUSH_FRIEND_SESSION: (self.on_push_friend_session, ACK_FRIEND_SESSION),
            PUSH_USER_MESSAGE: (self.on_push_user_message, ACK_USER_MESSAGE),
            ACK_USER_MESSAGE: (self._on_ack_user_message, None),
        }
        self._registered_callbacks: dict[
            WsAppEvent, tuple[Callable[[Any], None], tuple, dict]
        ] = {}

        self.friends: dict[int, Friend] = {}
        self.friend_list: SortedList[Friend] = SortedList(key=attrgetter("username"))

        self.timeline: deque[FriendRequestData] = deque()
        self.pending_friend_requests: dict[int, FriendRequestData] = {}
        self.pending_friend_confirms: dict[int, FriendConfirmData] = {}

        message_stream = MessageStream(request_timeout=5, ack_delay=0.5, loop=loop)
        message_stream.bind_ack_handler(self.collect_to_ack)
        message_stream.bind_timeout_handler(self.ack_timeout)
        self.message_stream = message_stream
        self.timeout_logs: dict[int, OutboundMessageLog] = {}

        self.chat_sessions: dict[int, ChatSession] = {}
        self.local_id_to_session: dict[int, ChatSession] = {}
        self.max_local_id = self.min_local_id = 1
        self.last_max_msg_id = 0

    def maybe_decay_local_ids(self, last_local_id: int):
        max_local_id, min_local_id = self.max_local_id, self.min_local_id
        if (last_local_id - min_local_id) / max_local_id > 0.65:
            local_ids_pop = self.local_id_to_session.pop
            for lid in range(min_local_id, last_local_id):
                local_ids_pop(lid, None)
            self.min_local_id = last_local_id

    def register_callback(
        self, event_tp, callback: Callable[[], None], *args, **kwargs
    ) -> None:
        self._registered_callbacks[event_tp] = (callback, args, kwargs)

    def schedule_callback(self, ws_event: WsAppEvent, **extra_fields) -> None:
        cb_item = self._registered_callbacks.get(ws_event)
        if cb_item is not None:
            cb, args, kwargs = cb_item
            kwargs.update(extra_fields)
            cb(*args, **kwargs)

    def raise_exception(self, status_code: int) -> None:
        self.schedule_callback(NETWORK_ERROR, status_code=status_code)

    def on_kicked_off(self):
        self.schedule_callback(KICKED_OFF, text="Sorry, kicked off by another device")

    def get_or_create_chat_session(self, friend: Friend):
        friend_id = friend.seq
        session = self.chat_sessions.get(friend_id)
        if session is not None:
            return session

        session = ChatSession(friend)
        session.bind(self)
        self.chat_sessions[friend_id] = session
        return session

    def collect_to_ack(self, pending: Iterable) -> None:
        acks = PubEventAckFromUser(logs=pending)
        self._writer_channel.put_nowait(
            PubEventFromUser(evt_tp=ACK_ACTION, payload=acks.SerializeToString())
        )

    def ack_timeout(self, message: Optional[OutboundMessageLog]):
        if message is None:  # Corner Check
            return

        receiver_id = message.receiver_id
        session = self.chat_sessions.get(receiver_id)

        local_id = message.delivery_id
        if local_id not in (timeout_logs := self.timeout_logs):
            # data updation if necessary
            timeout_logs[local_id] = message  # user session
            session.on_acked_timeout(local_id)  # chat_session

        # ui updation anyway
        self.schedule_callback(
            OUTBOUND_MESSAGE_TIMEOUT, receiver_id=receiver_id, local_id=local_id
        )

    def resend_message(self, text: str, *, delivery_id: int) -> None:
        msg_log = self.timeout_logs[delivery_id]
        assert delivery_id == self.message_stream.write(msg_log)  # expire_timer

        local_id_to_session = self.local_id_to_session
        if delivery_id not in local_id_to_session:
            local_id_to_session[delivery_id] = self.chat_sessions[msg_log.receiver_id]

        self._writer_channel.put_nowait(
            PubEventFromUser(
                evt_tp=PUSH_USER_MESSAGE,
                payload=ClientMsgData(
                    data=MsgData(
                        session_id=msg_log.session_id,
                        sender_id=msg_log.sender_id,
                        receiver_id=msg_log.receiver_id,
                        text=text,
                    ),
                    delivery_id=delivery_id,  # local increment
                ).SerializeToString(),
            )
        )

    def send_message(
        self,
        text: str,
        *,
        receiver_id: int,
        session_id: str,
    ) -> int:
        sender_id = self.user_seq
        msg_log = OutboundMessageLog(sender_id, receiver_id, session_id)
        delivery_id = self.message_stream.write(msg_log)  # new local_id

        if self.max_local_id < delivery_id:
            self.max_local_id = delivery_id
        self.local_id_to_session[delivery_id] = self.chat_sessions[receiver_id]

        msg_data_wrapper = PubEventFromUser(
            evt_tp=PUSH_USER_MESSAGE,
            payload=ClientMsgData(
                data=MsgData(
                    session_id=session_id,
                    sender_id=sender_id,
                    receiver_id=receiver_id,
                    text=text,
                ),
                delivery_id=delivery_id,  # local increment
            ).SerializeToString(),
        )
        self._writer_channel.put_nowait(msg_data_wrapper)
        return delivery_id

    # TODO offline message model
    # TODO stream queue corresponds to one dead-letter queue !!!
    # TODO message filter and order (Product)

    def on_push_user_message(self, event: PubEventToUser):
        logger.debug("received one message")
        # TODO use message_id to filter

        msg = ServerMsgData.FromString(event.evt_data)
        data = msg.data
        text, sender_id = data.text, data.sender_id

        session = self.chat_sessions[sender_id]
        local_id = self.message_stream.sender.borrow_virtual_local_id()
        if self.max_local_id < local_id:
            self.max_local_id = local_id

        message_id = msg.message_id
        if self.last_max_msg_id >= message_id:
            logger.warning("Found time disorder in message id")
        self.last_max_msg_id = message_id
        session.recv_message(text, local_id=local_id, message_id=message_id)

        self.schedule_callback(INBOUND_MESSAGE, sender_id=sender_id, local_id=local_id)

    def _on_ack_user_message(self, event: PubEventToUser):
        logger.debug("receiver one AckedMessage")

        delivery_id = event.log.delivery_id
        self.message_stream.on_acked(delivery_id)  # cancel timer

        session = self.local_id_to_session[delivery_id]
        self.maybe_decay_local_ids(delivery_id)

        # 1.data updation firstly
        self.timeout_logs.pop(delivery_id, None)  # pop anyway
        message_id = int.from_bytes(event.evt_data)  # 8B
        session.on_acked_success(delivery_id, message_id)
        if self.last_max_msg_id >= message_id:
            logger.warning("Found time disorder in message id")
        self.last_max_msg_id = message_id

        # 2.ui updation then
        self.schedule_callback(
            INBOUND_ACKED_MESSAGE, receiver_id=session.friend_id, local_id=delivery_id
        )

    # "channel_number", "evt_tp", "delivery_id", "evt_data"
    def on_push_friend_request(self, event: PubEventToUser):
        logger.debug("received a friend_request")

        request = FriendRequest.FromString(event.evt_data)
        link = request.link
        assert link.address_id == self.user_seq

        friend_id = link.request_id
        data = self.pending_friend_requests.get(friend_id)
        if data is None:  # needs to
            # maybe need to update mutable fields
            user = User(
                seq=friend_id,
                uid=UUID(bytes=request.uid, version=1),
                username=request.username,
                email=request.email,
            )

            data = FriendRequestData(user, state=RelationState.PENDING_INBOUND)
            if msg := request.request_msg:
                data.request_messages.append(msg)

            self.pending_friend_requests[friend_id] = data
            self.timeline.appendleft(data)

            self.schedule_callback(
                INBOUND_FRIEND_REQUEST,
                text=f"user {user.username} sent a friend request",
            )  # app.notify

        else:
            user = data.user
            match data.state:
                case RelationState.PENDING_OUTBOUND:  # Corner Case
                    pass
                case RelationState.PENDING_INBOUND:
                    pass
                case _:
                    pass

    def on_push_friend_confirm(self, event: PubEventToUser):
        logger.debug("received a friend_confirm")

        confirm = FriendConfirm.FromString(event.evt_data)
        link = confirm.link
        assert link.address_id == self.user_seq

        friend_id = link.request_id
        if friend_id in self.friends:
            return

        data = self.pending_friend_requests.get(friend_id)
        if data is None:
            return

        if confirm.action is ACCEPTED:
            data.state = ACCEPT_INBOUND

            user = data.user
            friend = Friend(user, confirm.session_id)
            self.friends[friend_id] = friend
            self.friend_list.add(friend)
            self.get_or_create_chat_session(friend)

            self.schedule_callback(
                INBOUND_FRIEND_CONFIRM, text=f"new friend {user.username}"
            )  # app.notify

    # def on_push_friend_session(self, event: PubEventToUser):
    #     logger.debug("received a friend_session")

    #     session = FriendSession.FromString(event.evt_data)
    #     link = session.link
    #     assert link.address_id == self.user_seq

    #     friend_id = link.request_id
    #     friend = self.friends.get(friend_id)
    #     if friend is None:
    #         return

    #     friend.session_id = session.session_id

    async def ws_connect(self):
        create_task = self._loop.create_task
        failures, backoff = 0, self._backoff
        async for protocol in self.ws_connect_helper(self.user_seq, self.access_token):
            if failures == 32:
                failures = 0

            writer_task: Task = create_task(self.writer(protocol))
            reader_task: Task = create_task(self.reader(protocol))
            reader_task.add_done_callback(lambda _: writer_task.cancel())

            self._writer_task = writer_task
            self._reader_task = reader_task
            try:
                await reader_task
            except ConnectionClosed as exc:
                # ConnectionClosedOk or ConnectionClosedError
                exc_code = exc.code
                if exc_code == WS_4007_KICKED_OFF:  # kicked off
                    self.on_kicked_off()
                    return
                elif exc_code == WS_4005_SEND_TOO_FAST:  # send too fast
                    await sleep(86400)
                elif exc_code == WS_1011_INTERNAL_ERROR:  # server internal error
                    logger.exception("Found uncaught exception in user read/write")
                    delay = backoff.compute(failures)
                    failures += 1
                    await sleep(delay / 3)  # maximum 3.3s
                elif exc_code == WS_1012_SERVICE_RESTART:
                    logger.exception("Found server shutdown.")
                    delay = backoff.compute(failures)  # maximum 10s
                    failures += 1
                    await sleep(delay)
                # never received 4004 for uvicorn's design
                elif exc_code == WS_4004_SERVER_SHUTDOWN:  # server shutdown
                    logger.exception("Found server shutdown.")
                    delay = backoff.compute(failures)  # maximum 10s
                    failures += 1
                    await sleep(delay)
                else:  # 1006 server actively closed, keepalive ?
                    logger.exception(
                        "Found uncaught exc_code: %s", exc_code, exc_info=exc
                    )
                    delay = backoff.compute(failures)  # maximum 10s
                    failures += 1
                    await sleep(delay)
            except CancelledError:
                logger.debug("`ws_connect` in `UserSession` needs to exit.")
                return
            except Exception as exc:  # TODO corner check
                logger.exception("Found exc in websocket.recv: ", exc)
                await sleep(2)  # auto-reconnect

    async def close(self):
        if (task := self._reader_task) is not None and not task.done():
            task.cancel()
            with suppress(CancelledError):
                await task

            self._reader_task = None
            self._writer_task = None

    async def reader(self, protocol: WebSocketClientProtocol) -> bool:
        message_stream = self.message_stream
        logs = message_stream.operation_log
        ready_to_ack = message_stream.read

        handlers = self._handlers
        while True:
            message = await protocol.recv()
            event = PubEventToUser.FromString(message)

            log = event.log
            handler, ack_tp = handlers[log.evt_tp]
            channel_number, delivery_id = log.channel_number, log.delivery_id
            if delivery_id not in logs[channel_number]:
                handler(event)
                logs[channel_number].add(delivery_id)

            if ack_tp is not None:
                ready_to_ack(
                    MessageLog(
                        evt_tp=ack_tp,
                        channel_number=channel_number,
                        delivery_id=delivery_id,
                    )
                )

    async def writer(self, protocol: WebSocketClientProtocol):
        channel_get = self._writer_channel.get
        try:
            while True:
                message = await channel_get()
                await protocol.send(message.SerializeToString())
        except ConnectionClosed as exc:
            raise ConnectionError(f"websocket lost: {exc}")
        except CancelledError:
            logger.debug("writer_task was cancelled.")

    def check_before_query_user(self, email: str) -> Optional[User]:
        curr_user = self._user
        if email == curr_user.email:
            return curr_user

        for friend in self.friends.values():
            curr_user = friend.user
            if email == curr_user.email:
                return curr_user

    def write_local_friend_request(self, user: User, request_msg: Optional[str] = None):
        address_id = user.seq
        data = self.pending_friend_requests.get(address_id)
        if data is None:
            data = FriendRequestData(user, state=RelationState.PENDING_OUTBOUND)
            self.pending_friend_requests[address_id] = data

        if request_msg is not None:
            data.request_messages.append(request_msg)

        self.timeline.appendleft(data)
        self.schedule_callback(OUTBOUND_FRIEND_REQUEST)

    def write_local_friend_confirm(
        self, seq: int, new_state: RelationState, *, session_id: Optional[int]
    ):
        data = self.timeline[seq - 1]
        data.state = new_state

        # TODO if delete or block before?
        if new_state is ACCEPT_INBOUND:
            user = data.user
            friend = Friend(user, session_id)
            self.friends[user.seq] = friend
            self.friend_list.add(friend)
            self.get_or_create_chat_session(friend)

    # TODO maybe add retry and notification support
    def hold_task(self, task: Task):
        tasks = self._async_tasks
        task.add_done_callback(tasks.discard)
        tasks.add(task)

    def collect_friend_list(self, json_resp: dict) -> dict[int, Friend]:
        friends_list = json_resp["data"]

        chat_sessions = self.chat_sessions
        friends, friend_list = self.friends, self.friend_list
        for item in friends_list:
            friend_id = item["seq"]
            session_id = item["session_id"]

            friend = Friend(
                User(
                    friend_id,
                    UUID(hex=item["uid"], version=1),
                    item["username"],
                    item["email"],
                ),
                session_id=session_id,
            )
            friends[friend_id] = friend
            friend_list.add(friend)

            session = ChatSession(friend)
            session.bind(self)
            chat_sessions[friend_id] = session
        return friends

    # TODO pagination here
    def collect_lastest_session(self, friend_id: int, data: list[dict]):
        virtual_local_id_sequence = self.message_stream.sender.borrow_virtual_local_id
        session = self.chat_sessions[friend_id]

        myself = self.user_seq
        for message in reversed(data):  # DESC storage over message_id
            local_id = virtual_local_id_sequence()
            message_id = message["message_id"]
            session.recv_message(
                message["text"],
                local_id=local_id,
                message_id=message_id,
                is_outbound=(message["sender_id"] == myself),
            )
        self.last_max_msg_id = message_id

    # TODO network broken?
    async def pull_session_messages(self):
        try:
            # Collect Friend List - wait friends data first
            friends = await self.scratch_friend_list()
        except BaseException as exc:  # may be timeout here?
            logger.exception("Found exc: %s", exc, exc_info=exc)
        else:
            num_friends = len(friends)
            friend_ids, session_ids = [None] * num_friends, [None] * num_friends
            for seq, (friend_id, friend) in enumerate(friends.items()):
                friend_ids[seq] = friend_id
                session_ids[seq] = friend.session_id
            await self.pull_sessions(friend_ids, session_ids)

    def collect_lastest_inbox(self, data: list[dict]):
        virtual_local_id_sequence = self.message_stream.sender.borrow_virtual_local_id
        chat_sessions = self.chat_sessions

        for message in reversed(data):  # DESC storage over message_id
            if (session := chat_sessions.get(message["sender_id"])) is None:
                logger.warning("Found messages which is not from your friend")
                continue

            if session.session_id != message.get("session_id"):
                logger.warning("Found unexpected session from Inbox, ignore it")
                continue

            local_id = virtual_local_id_sequence()
            message_id = message["message_id"]
            session.recv_message(
                message["text"],
                local_id=local_id,
                message_id=message_id,
            )

        if self.last_max_msg_id >= message_id:
            logger.warning("Found time disorder in message id")
        self.last_max_msg_id = message_id

    async def pull_offline_messages(self):
        try:
            data = await self.pull_inbox(self.last_max_msg_id)
        except BaseException as exc:  # may be timeout here?
            logger.exception("Found exc: %s", exc, exc_info=exc)
        else:
            self.collect_lastest_inbox(data)
