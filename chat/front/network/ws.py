from logging import getLogger
from enum import IntEnum
from typing import AsyncGenerator, Union
from asyncio import (
    CancelledError,
    TimeoutError as AsyncIOTimeoutError,
    BaseEventLoop,
    get_running_loop,
    sleep,
)

from websockets.legacy.client import Connect as WsConnect
from websockets.legacy.client import WebSocketClientProtocol
from websockets.exceptions import InvalidStatusCode

from utils.backoff import EqualJitterBackoff
from utils.exceptions import Rejected, Unavailable

logger = getLogger("ws-connection")


class WsConnectionState(IntEnum):
    READY = 1

    HANDSHAKE_INPROGRESS = 2
    HANDSHAKE_REJECTED = 3

    CONNECTED = 5

    OPEN_TIMEOUT = 8
    UNAVAILABLE = 9

    UNKNOWN_ERROR = 11


class WsConnection:
    __touched__ = ("ws_connect", "backoff", "_backoff")

    def __init__(self, host: str, port: int, loop: BaseEventLoop = None) -> None:
        self._host, self._port = host, port
        if loop is None:
            loop = get_running_loop()
        self._loop = loop
        self._backoff = EqualJitterBackoff(cap=5, base=0.25)

        self.state = WsConnectionState.READY

    async def ws_connect(
        self, headers: dict
    ) -> AsyncGenerator[WebSocketClientProtocol, Union[Rejected, Unavailable, None]]:
        ws_connect = WsConnect(
            f"ws://{self._host}:{self._port}/chatp",
            subprotocols=["chatp"],
            extra_headers=headers,
            open_timeout=3,
        )
        failures = 0
        backoff = self._backoff
        while True:
            self.state = WsConnectionState.HANDSHAKE_INPROGRESS
            try:  # ws_connect.__aenter__may raise certain exc.
                async with ws_connect as protocol:  # accepted
                    self.state = WsConnectionState.CONNECTED
                    yield protocol

            except AsyncIOTimeoutError:  # opentimeout in accept - network issue
                self.state = WsConnectionState.OPEN_TIMEOUT
                logger.info("ws handshake took too much time, then we need retry...")
                delay = backoff.compute(failures)
                failures += 1
                await sleep(delay)

            except CancelledError:  # cancelled when in handshake
                # client actively closed
                logger.warning("task was cancelled, exit now")
                self.state = WsConnectionState.READY
                break

            except InvalidStatusCode as e:  # handshake exc
                http_code = e.args[0]
                if http_code == 403:  # HTTP Forbidden, user auth failed
                    self.state = WsConnectionState.HANDSHAKE_REJECTED
                    logger.debug("Authenticate failed, needs relogin")
                    raise Rejected("UserAuth failed")
                elif http_code == 500:  # Handshake Failed / Server Shudown
                    self.state = WsConnectionState.UNAVAILABLE
                    logger.debug("WsGateway is unavailable now")
                    raise Unavailable("Server is down")  # uvicorn server is down
                else:  # TODO corner check
                    self.state = WsConnectionState.UNKNOWN_ERROR
                    raise

            except ConnectionRefusedError as e:  # tcp connection exc
                self.state = WsConnectionState.UNAVAILABLE
                logger.warning("Server is unavailable")

                delay = backoff.compute(failures)
                failures += 1
                await sleep(delay)

            except ConnectionResetError as e:
                self.state = WsConnectionState.UNAVAILABLE
                logger.warning("Connection is reset.")

                delay = backoff.compute(failures)
                failures += 1
                await sleep(delay)

            except Exception as exc:
                logger.warning(f"Found exc in websockets.connect: {exc}")
                break
            else:  # never comes here
                pass
