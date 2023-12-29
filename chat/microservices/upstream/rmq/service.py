from enum import IntEnum
from functools import partial
from logging import getLogger
from dataclasses import dataclass
from typing import Callable, Optional, AsyncContextManager

from asyncio import (
    TimeoutError as AsyncIOTimeoutError,
    CancelledError,
    Future,
    wait_for,
)
from google.protobuf.message import Message as ProtobufMessage
from rstream.producer import ConfirmationStatus

from chatp.rmq.stream.backend import RMQStreamBackend
from chatp.rmq.stream.producer import RMQStreamProducer


logger = getLogger("RMQService")
logger.setLevel(10)


class RMQState(IntEnum):
    IDLE = 0
    RUNNING = 1
    CLOSING = 2
    CLOSED = 3


@dataclass
class MessageWrapper:
    data: ProtobufMessage
    waiter: Future
    publishing_id: Optional[int] = None

    def __bytes__(self):
        return self.data.SerializeToString()

    def __hash__(self):
        return self.waiter.__hash__()


def routing_extractor_wrapper(
    route_func: Callable[[ProtobufMessage], str]
) -> Callable[[MessageWrapper], str]:
    return lambda msg: route_func(msg.data)


class MessageTracerBase:
    __slots__ = ()

    async def conflict_check(self, message, *, timeout):
        pass

    def on_publish_start(self, message):
        pass

    def on_publish_success(self, message):
        pass

    def on_publish_failure(self, message):
        pass


class RMQService(AsyncContextManager):
    backend: RMQStreamBackend
    producer: RMQStreamProducer
    waiters: set[MessageWrapper]  # used to inform user

    tracer: Optional[MessageTracerBase] = None
    done_cb: Optional[Callable[[ProtobufMessage], None]] = None
    err_cb: Optional[Callable[[ProtobufMessage], None]] = None
    routing_extractor: Optional[Callable[[MessageWrapper], str]] = None

    def __init__(self, setting: dict) -> None:
        self.setting = setting
        self.waiters: set[MessageWrapper] = set()
        self.state = RMQState.IDLE

    def bind_tracer(self, tracer: MessageTracerBase):
        self.tracer = tracer
        self.bind_callbacks(tracer.on_publish_success, tracer.on_publish_failure)

    def bind_route_func(self, route_func: Callable[[ProtobufMessage], str]):
        self.routing_extractor = routing_extractor_wrapper(route_func)

    def bind_callbacks(
        self,
        done_cb: Callable[[ProtobufMessage], None],
        err_cb: Callable[[ProtobufMessage], None],
    ):
        self.done_cb = done_cb
        self.err_cb = err_cb

    def publish_confirm_cb(
        self, confirmation: ConfirmationStatus, message: MessageWrapper
    ):
        if confirmation.is_confirmed:
            if not (waiter := message.waiter).done():
                waiter.set_result(None)
            if (done_cb := self.done_cb) is not None:
                done_cb(message.data)
        else:  # wait user to find timeout
            resp_code = confirmation.response_code
            logger.warning(f"Failed to Push: {resp_code}")
            if (err_cb := self.err_cb) is not None:
                err_cb(message.data)

    async def publish_message(self, message: ProtobufMessage, *, timeout: int = 5):
        if self.state >= RMQState.CLOSING:
            return False

        if (tracer := self.tracer) is not None:
            tracer.on_publish_start(message)

        waiter = Future()
        msg_wrapper = MessageWrapper(message, waiter)
        self.waiters.add(msg_wrapper)
        waiter.add_done_callback(lambda _: self.waiters.discard(msg_wrapper))

        try:
            # Anyway, message is always inflight, wait to sent out, unless RStream is down
            # But we assume that RStream will never go offline (like the Redis)
            await self.send_message(msg_wrapper)
            await wait_for(waiter, timeout)
            return True
        except AsyncIOTimeoutError:
            # waiter was cancelled due to timeout, but wait_for raise AsyncIOTimeoutError
            logger.warning("Found timeout in `publish_message`")
            return False
        except (CancelledError, Exception) as exc:  # Exception is unnecessary but keeps
            # waiter was cancelled by the peer or server shutdown
            if not waiter.done():
                waiter.set_exception(exc)
            return False

    async def __aenter__(self):
        if (routing_extractor := self.routing_extractor) is None:
            raise Exception("RMQService missed `routing_extractor`")

        setting = self.setting
        self.backend = backend = RMQStreamBackend(
            host=setting["RMQ_STREAM_HOST"],
            port=setting["RMQ_STREAM_PORT"],
            username=setting["RMQ_STREAM_USERNAME"],
            password=setting["RMQ_STREAM_PASSWORD"],
        )

        super_stream_producer: RMQStreamProducer = await backend.create_producer(
            super_stream=setting["RMQ_STREAM_NAME"],
            routing_extractor=routing_extractor,
            default_batch_publishing_delay=0.1,
            broker_name=setting["PLATFORM_ID"],
        )
        self.producer = super_stream_producer

        self.send_message = partial(
            super_stream_producer.send, on_publish_confirm=self.publish_confirm_cb
        )
        self.state = RMQState.RUNNING
        return self

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        # TODO Inflight Messages required to be sent out
        # rstream library is responsible for this, Optimize Later

        self.state = RMQState.CLOSING
        await self.backend.__aexit__(exc_tp, exc_val, exc_tb)
        self.state = RMQState.CLOSED
