from logging import getLogger
from typing import Optional, Callable, Coroutine
from asyncio import create_task, wait, sleep, Task
from inspect import iscoroutinefunction

from .loadbalance import LoadBalancer
from ..rpc.grpc_service import GrpcService
from ..multiprocess.base import BaseWorkerProcess
from ..proto.processes.event_pb2 import (
    Event as ProcEvent,
    LoadHintEvent,
    ServiceEvent,
    EventType,
    USER_EVENT,
    LOAD_HINT,
    SERVICE_CHANGE,
    SERVICE_ONLINE,
    SERVICE_OFFLINE,
)

logger = getLogger("GrpcClientManager")
logger.setLevel(10)


def event_handler(handlers: dict[EventType, Callable[[ProcEvent], Coroutine]]):
    async def _inner_impl(event: ProcEvent):
        handler = handlers.get(event.evt_tp)
        if handler is not None:
            try:
                if iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except BaseException as exc:
                logger.exception(
                    "Found exc when interacting with master: %s", exc, exc_info=exc
                )

    _inner_impl.__name__ = "event_handler"
    _inner_impl.__qualname__ = "chatp.manager.grpc_client.event_handler"
    return _inner_impl


class GrpcClientManager:
    _task: Task

    __slots__ = (
        "find_service",
        "read_cb",
        "write_cb",
        "multi_work_mode",
        "bidirectional",
        "_proc",
        "_task",
    )

    def __init__(
        self,
        multi_work_mode: bool = False,
        bidirectional: bool = True,
    ):
        self.multi_work_mode = multi_work_mode
        self.bidirectional = bidirectional

    def post_initialize(
        self,
        proc: BaseWorkerProcess,
        load_manager: LoadBalancer,
        *,
        user_handler: Optional[Callable[[bytes], None]] = None,
    ):
        self._proc = proc

        handlers = {
            SERVICE_CHANGE: self.service_event_cb,
            LOAD_HINT: load_manager.load_event_cb,
            USER_EVENT: user_handler,
        }
        self.read_cb = event_handler(handlers)
        self.write_cb = load_manager.write_load_back
        self.find_service = load_manager.route

    def service_event_cb(self, proc_event: ProcEvent):
        event: ServiceEvent = proc_event.srv_evt
        if (srv_tp := event.srv_tp) is SERVICE_ONLINE:
            GrpcService.bind(event.srv_name, event.srv_addr)
        elif srv_tp is SERVICE_OFFLINE:
            GrpcService.unbind(event.srv_name, event.srv_addr)
        else:  # currently, never comes here
            pass

    async def __aenter__(self):
        self._task = create_task(
            self._proc.interact_with_master(self.write_cb, self.read_cb)
        )
        GrpcService.inject(self)
        return self

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        if (task := self._task) is not None:
            self._task = None
            task.cancel()
            await wait([task])
            await sleep(0)

        if self.bidirectional:
            await GrpcService.close()
