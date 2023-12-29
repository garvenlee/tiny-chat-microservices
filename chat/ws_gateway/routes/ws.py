from logging import getLogger
from time import monotonic
from typing import Optional
from asyncio import CancelledError, create_task

# from memory_profiler import profile
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from chatp.multiprocess.worker import WorkerProcess
from chatp.manager.grpc_client import GrpcClientManager
from chatp.redis.client import RedisClient
from chatp.proto.services.push.push_pb2 import PUSH_USER_KICKED_OFF

from manager.tasks import TaskManager
from manager.session import WebsocketSession, SessionManager

# from rpc.redis_service import RedisService
from rpc.push_service import PushService
from rpc.proto.ws_pb2 import StatusFrame
from utils.exceptions import InvalidRate
from utils.model import *


logger = getLogger("WebsocketEndpoint")
logger.setLevel(10)

before_handshake = WebsocketSession.before_handshake
websocket_upgrade = WebsocketSession.websocket_upgrade


# @profile
async def websocket_endpoint(websocket: WebSocket):
    state = websocket.state
    ws_manager: SessionManager = state.ws_manager
    if ws_manager.shutdown:  # fast shield
        return

    payload = await before_handshake(
        websocket, websocket.headers, ws_manager.APPID_PREFIX
    )
    if payload is not None:
        uid, device_name, auth_field, appid = payload
        # uid = random.randint(1, 1000000)
        device_tp = SessionManager.DEVICE_MAPPING[device_name]
        session_key = uid * SessionManager.DEVICE_KINDS_NUM + device_tp

        redis_service: RedisClient = state.redis_client

        # distributed concurrency WsLogin - Redis Setnx
        login_lock = f"chatp:ws:login:confilct_lock:{session_key}"
        async with ws_manager.lock_session(login_lock, redis_service) as locked:
            if locked:
                if ws_manager.shutdown:  # fast shield
                    return

                grpc_manager: GrpcClientManager = state.grpc_manager
                try:
                    success = await websocket_upgrade(
                        websocket, grpc_manager, auth_field
                    )
                except ConnectionClosed as exc:
                    logger.error(
                        "Found ConnectionClosed in `websocket_upgrade`: %s",
                        exc,
                        exc_info=exc,
                    )
                    return
                except BaseException as exc:
                    logger.error(
                        "Found exc in `websocket_upgrade`:  %s", exc, exc_info=exc
                    )
                    await websocket.close(WS_1011_INTERNAL_ERROR)
                    return
                else:
                    if not success:
                        return
                    elif (session := ws_manager.get(session_key)) is None:
                        session = ws_manager.create_session(
                            websocket, session_key, device_tp, appid
                        )

                        addr_key = f"chatp:user:gateway_addr:uid:{uid}"
                        is_kicked: Optional[bool] = await session.check_multi_devices(
                            websocket, redis_service, addr_key, device_name
                        )
                        if is_kicked is None:  # no conflict with multi-terminal
                            logger.info(
                                "No another terminal of the same UserDeviceType."
                            )
                            if (
                                not await session.activate(
                                    redis_service, addr_key, device_name
                                )
                                or ws_manager.shutdown
                            ):
                                ws_manager.recycle_session(session_key)
                                return

                            try:
                                await websocket.send_bytes(
                                    StatusFrame(
                                        kicked_off=False,
                                        extra=bytes(session.wsid, "ascii"),
                                    ).SerializePartialToString()
                                )
                            except (ConnectionClosed, Exception):
                                ws_manager.recycle_session(session_key)
                                await session.deactivate(
                                    redis_service, addr_key, device_name
                                )
                                return
                        elif (
                            is_kicked
                        ):  # the kicked's conn isn't in current SessionManager
                            # 1.Firstly, Grpc-Call<PushData> to kick the connection in another gateway
                            push_service: PushService = grpc_manager.find_service(
                                "PushService"
                            )
                            if push_service is None:
                                ws_manager.recycle_session(session_key)
                                await websocket.close(WS_1013_TRY_AGAIN_LATER)
                                return

                            checkpoint = monotonic()
                            if (
                                not await push_service.push_data(
                                    data_type=PUSH_USER_KICKED_OFF,
                                    address_id=uid,
                                    payload=device_tp.to_bytes(),
                                    timeout=5,
                                )
                                or ws_manager.shutdown
                            ):
                                ws_manager.recycle_session(session_key)
                                await websocket.close(WS_1013_TRY_AGAIN_LATER)
                                return
                            logger.info(
                                f"Already kicked another session, [{monotonic() - checkpoint}]"
                            )

                            # 2.Secondly, update the redis-online-status with current GatewayAddr
                            if (
                                not await session.activate(
                                    redis_service, addr_key, device_name
                                )
                                or ws_manager.shutdown
                            ):
                                ws_manager.recycle_session(session_key)
                                return

                            try:
                                await websocket.send_bytes(b"1")
                            except (ConnectionClosed, Exception):
                                ws_manager.recycle_session(session_key)
                                await session.deactivate(
                                    redis_service, addr_key, device_name
                                )
                                return
                        else:  # redis check exc or lost connection
                            ws_manager.recycle_session(session_key)
                            return

                        task_manager: TaskManager = state.task_manager

                    elif await session.negotiate_kick_off(websocket):
                        task_manager: TaskManager = state.task_manager
                        task_manager.cancel(session_key)  # next eventloop
                        session.state = SESSION_CLOSING  # reuse user_addr in redis
                        if await ws_manager.wait_for_recycle(session_key, timeout=5):
                            logger.info(
                                "Already kicked another session in the same process."
                            )
                            session = ws_manager.reuse_session(session_key)
                            if session is None:
                                await websocket.close(WS_1011_INTERNAL_ERROR)
                                return

                            try:
                                await websocket.send_bytes(b"1")
                            except (ConnectionClosed, Exception):
                                ws_manager.retrieve_session(session_key)
                                return
                            else:  # already kicked another
                                addr_key = f"chatp:user:gateway_addr:uid:{uid}"
                                session.rebind(websocket, session_key, device_tp, appid)
                        else:  # timeout
                            await websocket.close(WS_1013_TRY_AGAIN_LATER)
                            return

                    else:  # dont kick off or found exc
                        return

            elif locked is not None:  # setnx found conflict
                await websocket.accept("chatp")
                await websocket.close(
                    WS_4008_CONNECT_CONFLICT,
                    reason="Another device is attempting to login.",
                )
                return

            else:  # REDIS_TIMEOUT or REDIS_FAILED
                await websocket.accept("chatp")
                await websocket.close(
                    WS_1013_TRY_AGAIN_LATER,
                    reason="RedisClient May be Busy!",
                )
                return

        proc: WorkerProcess = state.proc
        logger.info(f"Accepted new WsConnection [{proc.pid}]")

        # Current Design
        # For each user, there are four tasks:
        # 1.ws view task in uvicorn - ends with `read_message`
        # 2.read_message - mainloop, read from user
        # 3.write_message - cancelled when `read_message` is done
        # 4.deliver_message in read_message.<locals>, ends with `read_message`
        writer_task = create_task(session.write_messages(session_key))
        reader_task = task_manager.create_task(
            session_key,
            session.read_messages(
                ws_manager.channel_queue, ws_manager.transfer_service_getter
            ),
        )
        reader_task.add_done_callback(lambda _: writer_task.cancel())
        reader_task.add_done_callback(lambda _: ws_manager.recycle_session(session_key))

        try:
            await reader_task  # now, endpoint task monitor the read_message task
        except CancelledError:  # user_kicked_off or server shutdown
            if ws_manager.shutdown:
                session.state = SESSION_CLOSED
                # transport was already closed, no need to call close
            else:
                # now state is SESSION_CLOSING
                await websocket.close(
                    code=WS_4007_KICKED_OFF, reason="User was kicked off."
                )
        except WebSocketDisconnect as exc:
            session.state = SESSION_CLOSED
            logger.info(f"Checked that the peer has disconnected, code: {exc.code}")
        except InvalidRate:
            # TODO banned info - now just banned the user's all sending ability
            logger.warning("send too fast, must banned")
            session.state = SESSION_CLOSED
            await websocket.close(
                code=WS_4005_SEND_TOO_FAST,
                reason="Messages were sent too quickly, please wait one day before sending the next message",
            )
        except BaseException as exc:  # bug here?
            logger.error("found exc in ReadTask: %s", exc, exc_info=exc)
            session.state = SESSION_CLOSED
            await websocket.close(
                code=WS_1011_INTERNAL_ERROR, reason="Internal Exception"
            )
        else:
            session.state = SESSION_CLOSED
            await websocket.close()
        finally:
            if session.state is SESSION_CLOSED:
                await session.deactivate(redis_service, addr_key, device_name)
