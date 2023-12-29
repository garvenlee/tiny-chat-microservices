from random import _inst
from enum import IntEnum
from time import monotonic
from json import dumps
from logging import getLogger
from itertools import repeat
from functools import partial, wraps
from operator import attrgetter
from collections import defaultdict
from itertools import cycle, islice
from typing import Any, Callable, Coroutine, Optional, Union

from asyncio import (
    get_running_loop,
    create_task,
    wait,
    gather,
    sleep,
    Future,
    Task,
    TimerHandle,
    CancelledError,
)
from anyio._core._tasks import move_on_after
from aiomisc.circuit_breaker import CircuitBreaker
from grpc import RpcError, ChannelConnectivity
from grpc.aio._channel import _BaseMultiCallable, Channel, insecure_channel
from opentelemetry.instrumentation.grpc import aio_client_interceptors

# from grpc._cython._cygrpc import UsageError
# from uhashring import HashRing
from hash_ring_rs import HashRing

from ..utils.types import ServiceName, ServiceAddr, StubClassType, GrpcManager
from ..utils.circuit_breaker import CircuitBreakerMixin
from .grpc_wrapper import (
    exception_inspector,
    grpc_wrapper_with_kwargs,
    grpc_wrapper_with_request,
)

randbelow = _inst._randbelow
logger = getLogger("GrpcService")
logger.setLevel(10)

MAX_INT32 = 2 << 32 - 1


class ChannelState(IntEnum):
    IDLE = 1
    ALIVE = 2

    SUBJECT_REBUILD = 4  # tag double check later
    SUBJECT_DOWN = 8  # after double check, still not READY

    ETCD_REPORT_UP = 16
    ETCD_REPORT_DOWN = 32


def print_exc_info(fut: Future, *, info_template: str):
    if not fut.cancelled() and (exc := fut.exception()) is not None:
        logger.exception(info_template, exc, exc_info=exc)


class GrpcStub:
    retries: int = 3
    rebuild_intervals: int = 10
    graceful_shutdown_time: int = 8
    hibernate_seconds: int = 60
    hibernate_timer: Optional[TimerHandle] = None

    create_func: Callable
    create_args: tuple
    create_kwargs: dict
    initialize_args: tuple

    is_new_one: bool = False
    create_bound: bool = False

    def __init__(
        self,
        channel: Optional[Channel] = None,
        stub: Optional[StubClassType] = None,
    ):
        self._channel = channel
        self._stub = stub

    # After grpc_channel is created (called insecure_channel or secure_channel),
    # `get_state()` gets IDLE, but `get_state(try_to_connect=True)` gets CONNECTING,
    # and then must wait it to change to READY or TRANSIENT_FAILURE, which consumes some time slices
    # for TCP handshake, HTTP2 negotiate etc.
    #
    # If GOAWAY is received, get_state -> IDLE, but with `try_to_connect=True` -> TRANSIENT_FAILURE
    # If channel is already healthy in most cases, `get_state()` will fastly return READY
    #
    # Currenly, TRANSIENT_FAILURE is regarded as service offline
    #
    # TODO ReCheck: whether try_to_connect=True will block the whole EventLoop
    @property
    def is_health(self):
        channel = self._channel
        return (
            channel is not None  # insecure_channel raises exc s.t. Resource Unavailable
            and channel.get_state(try_to_connect=True) is ChannelConnectivity.READY
        )

    @property
    def is_lost(self):
        channel = self._channel
        return channel is None or (
            not self.in_hibernate  # already reconnected too many times, but dont received DOWN
            and channel.get_state(try_to_connect=True) is not ChannelConnectivity.READY
        )

    @property
    def in_hibernate(self):
        return self.hibernate_timer is not None

    @property
    def initialized(self):
        return self._channel is not None

    @classmethod
    def create(cls, create_func: Callable, create_args: tuple, create_kwargs: dict):
        stub = cls()
        stub.create_func = create_func
        stub.create_args = create_args
        stub.create_kwargs = create_kwargs
        stub.create_bound = True
        return stub

    def exit_hibernate(self):
        assert self.hibernate_timer.when() < monotonic()
        self.hibernate_timer = None
        self.retries = 3
        logger.warning("GrpcStub exits hibernate")

    def begin_hibernate(self, delay: int):
        self.hibernate_timer = get_running_loop().call_later(delay, self.exit_hibernate)

    async def wait_for_initialized(self):
        if self.initialized:
            return

        create_func = self.create_func
        create_args = self.create_args
        create_kwargs = self.create_kwargs
        while not self.initialized:
            try:
                stub: "GrpcStub" = create_func(*create_args, **create_kwargs)
            except BaseException as exc:
                logger.warning(
                    "Found exception in `create_stub`: %s", exc, exc_info=exc
                )
                await sleep(5)
            else:
                self._channel = stub._channel
                self._stub = stub._stub
                del stub
                self.initialize(*self.initialize_args)
                break

    async def wait_for_ready(self):  # return when channel is ready or raise exc if any
        try:
            await self._channel.channel_ready()
        except CancelledError:
            raise
        except BaseException as exc:  # s.t. UsageError("Channel is closed")
            logger.exception(
                "Found exception when reconnecting to GrpcServer: %s",
                exc,
                exc_info=exc,
            )
            return False
        else:
            return True

    async def reconnect(self, timeout: int = 5):
        if self.in_hibernate:
            return False

        self.retries -= 1
        if self.retries == 0:
            delay = (
                self.rebuild_intervals
                if self._channel is None
                else self.hibernate_seconds
            )
            self.begin_hibernate(delay)
            logger.warning("GrpcStub enters hibernate, wait %s seconds", delay)
            return False

        is_new_one = False
        if self._channel is None:
            logger.warning("GrpcStub needs to rebuild")
            stub: "GrpcStub" = self.create_func(*self.create_args, **self.create_kwargs)
            # dont capture exc, `self._channel`` is still None if there is any exc, then
            # monitor_task will reach here later, attempt to reconnect again unless ETCD server
            # founds this service is down, then remove it[Addr: GrpcStubGroup]
            # or reaches max retries, then must be in hibernate, only considered network partition
            self._channel = stub._channel
            self._stub = stub._stub
            del stub
            self.initialize(*self.initialize_args)
            self.is_new_one = is_new_one = True

        with move_on_after(timeout) as scope:
            if await self.wait_for_ready():  # dont shield CancelledError
                logger.info("GrpcStub channel can be reused")
                # here, hibernate_timer must be None
                if self.retries < 3:
                    self.retries = 3
            else:  # needs to rebuild this channel
                logger.warning("GrpcStub needs to create one new channel")
                stub: "GrpcStub" = self.create_func(
                    *self.create_args, **self.create_kwargs
                )

                old_channel = self._channel
                self._channel = stub._channel
                self._stub = stub._stub
                del stub
                self.initialize(*self.initialize_args)

                if not old_channel._channel.closed():  # TODO ReCheck
                    uncontrolled_task = get_running_loop().create_task(
                        old_channel.close()
                    )
                    uncontrolled_task.add_done_callback(
                        partial(
                            print_exc_info,
                            info_template="Found exception in `channel.close`: %s",
                        )
                    )
                self.is_new_one = is_new_one = True
                self._channel.get_state(try_to_connect=True)  # weak connect

        if scope.cancel_called:
            logger.warning("Found timeout in reconnect")
        return is_new_one  # possibly not ready now

    def initialize(
        self, srv_name: str, service_cls: "GrpcService", circuit_breaker: CircuitBreaker
    ):
        stub = self._stub
        if stub is None:
            if not hasattr(self, "initialize_args"):
                self.initialize_args = (srv_name, service_cls, circuit_breaker)
            return

        if reuse := service_cls.reuse:  # directly borrow
            for meth_name in reuse:
                if (
                    stub_meth := getattr(stub, meth_name, None)  # bound method
                ) is not None:
                    setattr(self, meth_name, stub_meth)

        if wrapped_directly := service_cls.wrapped_directly:  # with error handler
            for meth_name in wrapped_directly:
                stub_meth = getattr(stub, meth_name, None)  # bound method
                if stub_meth is not None:
                    setattr(
                        self,
                        meth_name,
                        grpc_wrapper_with_request(
                            stub_meth, meth_name, srv_name, circuit_breaker
                        ),
                    )

        if wrapped_with_combination := service_cls.wrapped_with_combination:
            service_cls_dict = service_cls.__dict__
            for meth_name in wrapped_with_combination:
                stub_meth = getattr(stub, meth_name, None)  # bound method
                if stub_meth is not None:
                    meth_definition = service_cls_dict[meth_name]
                    setattr(
                        self,  # each instance has its service method, which channel is different
                        meth_name,
                        # func' self is a instance of `UserStub`
                        grpc_wrapper_with_kwargs(
                            stub_meth, meth_definition, srv_name, circuit_breaker
                        ),
                    )

        if customization := service_cls.customization:
            for meth_name in customization:
                meth = getattr(service_cls, meth_name, None)
                if meth is not None and isinstance(
                    stub, meth.__annotations__["depend_stub"]
                ):  # Safe type check in GrpcService.__init_subclass__
                    setattr(
                        self,
                        meth_name,
                        # here must rebound args `self` to current object
                        # it cannot be `self=self`!!!
                        partial(meth, self),
                    )

    @classmethod
    def is_service(cls, obj: Any) -> bool:
        # stub.method is a class insatnce, which class is like
        # grpc.aio._channel.##MultiCallable
        return isinstance(obj, _BaseMultiCallable)

    def reset(self):
        self._channel = self._stub = None

    async def close(self):
        channel = self._channel
        if channel is not None:
            self._channel = None
            self._stub = None

            try:
                await channel.close(self.graceful_shutdown_time)
            except BaseException as exc:
                logger.exception(
                    "Found exc when closing the underlaying channel: %s",
                    exc,
                    exc_info=exc,
                )
        elif self.in_hibernate:
            timer, self.hibernate_timer = self.hibernate_timer, None
            timer.cancel()


def shield_connection_error(wrapped: Callable):
    @wraps(wrapped)
    def _inner_impl(*args, **kwargs) -> GrpcStub:
        try:
            stub = wrapped(*args, **kwargs)
        except BaseException as exc:
            logger.exception(
                "Found exc in `insecure_channel` method: ", exc, exc_info=exc
            )
            stub = GrpcStub.create(wrapped, args, kwargs)
        return stub

    return _inner_impl


class RoundRobin:
    __slots__ = "items", "index"

    def __init__(self, items: Optional[list] = None):
        self.index = 0
        if items is None:
            items = []
        self.items = items

    def add(self, srv):
        self.items.append(srv)

    def remove(self, srv):
        self.items.remove(srv)

    def decay(self):
        if (idx := self.index) > MAX_INT32:
            idx -= MAX_INT32
            self.index = idx

    def flick(self):
        items = self.items
        num_items = len(items)
        pos = self.index % num_items
        for stub in islice(cycle(items), pos, pos + num_items):
            self.index += 1
            yield stub


# TODO grpc connection is lost?
# one addr -> serveral channel stub
# here, make stubs a dict, then all is fine?
class GrpcStubGroup(CircuitBreakerMixin):
    __slots__ = (
        "state",
        "addr",
        "stub_name",
        "stubs",
        "linked_stubs",
        "channel_options",
        "max_channels",
        "round_robin_index",
    )

    exceptions = (RpcError,)

    ERROR_RATIO: float = 0.2
    RESPONSE_TIME: int = 10
    PASSING_TIME: int = 5
    BROKEN_TIME: int = 10
    RECOVERY_TIME: int = 5

    default_channel_options = [
        # ("grpc.so_reuseport", 1),  # default 1
        # ("grpc.max_connection_idle_ms", 120_000),  # 2min
        # ("grpc.max_connection_age_ms", 5_000),  # 5s
        # ("grpc.min_reconnect_backoff_ms", 50),
        # ("grpc.max_reconnect_backoff_ms", 300),
        ("grpc.keepalive_time_ms", 10_000),  # 10s
        ("grpc.keepalive_timeout_ms", 5_000),  # 5s
        ("grpc.http2.max_pings_without_data", 5),
        ("grpc.keepalive_permit_without_calls", 1),
        ("grpc.enable_retries", 1),
        # ("grpc.max_retries", 3),  # connection retry
        (
            "grpc.service_config",
            dumps(
                {
                    "methodConfig": [
                        {
                            "name": [{}],  # all methods use the same policy
                            "retryPolicy": {
                                "maxAttempts": 3,
                                "initialBackoff": "0.05s",
                                "maxBackoff": "0.5s",
                                "backoffMultiplier": 2,
                                "retryableStatusCodes": ["UNAVAILABLE"],
                            },
                        }
                    ]
                }
            ),
        ),
    ]

    def __init__(
        self,
        addr: str,
        *,
        max_channels: int = 4,
        channel_options: Optional[dict] = None,
    ):
        self.state = ChannelState.IDLE

        self.addr = addr
        self.stub_name: Optional[str] = None
        self.stubs: Optional[list[GrpcStub]] = None
        self.linked_stubs: Optional[dict[str, list[GrpcStub]]] = None
        self.round_robin_index = 0

        self.max_channels = max_channels
        if channel_options is None:
            channel_options = self.default_channel_options
        self.channel_options = channel_options

    @property
    def is_down(self):
        return self.state & (ChannelState.SUBJECT_DOWN | ChannelState.ETCD_REPORT_DOWN)

    def copy_from(
        self,
        src_stubs: list[GrpcStub],
        dest_stub_cls,
        *,
        srv_name: str,
        srv_cls: "GrpcService",
    ):
        stubs = []
        stubs_append = stubs.append
        for src_stub in src_stubs:
            channel = src_stub._channel
            stub = dest_stub_cls(channel) if channel is not None else None
            grpc_stub = GrpcStub(channel, stub)
            grpc_stub.initialize(srv_name, srv_cls, self._circuit_breaker)
            stubs_append(grpc_stub)
        return stubs

    def initialize(self, srv_name: str, srv_cls: "GrpcService"):
        self.cb_initialize(exception_inspector=exception_inspector)

        create_stub = self.create_stub
        addr, bind_stub = self.addr, srv_cls.__bind_stub__

        before_channel_created = srv_cls.before_channel_created
        after_channel_created = srv_cls.after_channel_created

        if isinstance(bind_stub, (list, tuple)):
            main_stub, sibling_stubs = bind_stub[0], bind_stub[1:]
        else:
            main_stub, sibling_stubs = bind_stub, None

        self.stubs = stubs = [
            create_stub(addr, main_stub, before_channel_created, after_channel_created)
            for _ in repeat(None, self.max_channels)
        ]
        for stub in stubs:
            stub.initialize(srv_name, srv_cls, self._circuit_breaker)
        self.stub_name = main_stub.__name__

        if sibling_stubs is not None:  # share the underlaying channel
            linked_stubs = {}
            copy_from = self.copy_from
            for stub_cls in sibling_stubs:
                linked_stubs[stub_cls.__name__] = copy_from(
                    stubs, stub_cls, srv_name=srv_name, srv_cls=srv_cls
                )
            self.linked_stubs = linked_stubs

    @shield_connection_error
    def create_stub(
        self,
        addr: str,
        bind_stub: StubClassType,
        before_created: Optional[Callable[[], None]],
        after_created: Optional[Callable[[StubClassType], Coroutine]],
    ) -> GrpcStub:
        if before_created is not None:
            before_created()

        # must create channel, used to create stub instance
        # grpcio stub __init__: add grpc methods to the self
        channel = insecure_channel(
            addr,
            options=self.channel_options,
            interceptors=aio_client_interceptors(),
        )

        if after_created is not None:
            try:
                after_created(stub)
            except BaseException as exc:
                logger.exception(
                    "Found exc in `after_channel_created`: %s", exc, exc_info=exc
                )
                create_task(channel.close(10))
                raise

        stub = bind_stub(channel)
        return GrpcStub(channel, stub)

    def check_if_any_healthy(self):
        return any(stub.is_health for stub in self.stubs)

    def rebuild_if_needs(self):  # recheck if it's offline
        create_task = get_running_loop().create_task
        stubs = filter(attrgetter("is_lost"), self.stubs)
        return [create_task(stub.reconnect()) for stub in stubs]

    def get(self, domain: Optional[str] = None) -> GrpcStub:
        if (stubs := self.stubs) is None:
            raise Exception("UsageError: still not initialized yet")

        if domain is not None:
            if (linked_stubs := self.linked_stubs) is None:
                raise NotImplementedError(f"Need to bind {domain}")
            stubs = linked_stubs.get(domain)
            if stubs is None:
                raise NotImplementedError(f"Need to bind {domain}")

        rb_idx = self.round_robin_index
        num_stubs = self.max_channels
        try:
            for idx in range(rb_idx, rb_idx + num_stubs):
                stub: GrpcStub = stubs[idx % num_stubs]
                if stub.is_health:
                    return stub
        finally:
            self.round_robin_index = idx + 1

    def decay_rb(self):
        rb_idx = self.round_robin_index
        if rb_idx > MAX_INT32:
            rb_idx -= MAX_INT32
            self.round_robin_index = rb_idx

    async def close(self):
        if (stubs := self.stubs) is not None:
            self.stubs = None
            await wait([create_task(stub.close()) for stub in stubs])
            if (linked_stubs := self.linked_stubs) is not None:
                self.linked_stubs = None
                for stub_list in linked_stubs.values():
                    for stub in stub_list:
                        stub.reset()
                linked_stubs.clear()


class GrpcStubGroupWithTask(GrpcStubGroup):
    __slots__ = "service_consumer_task"

    def initialize(self, srv_name: str, srv_cls: "GrpcService"):
        self.cb_initialize(exception_inspector=exception_inspector)

        create_stub = self.create_stub
        addr, bind_stub = self.addr, srv_cls.__bind_stub__

        before_channel_created = srv_cls.before_channel_created
        after_channel_created = srv_cls.after_channel_created

        self.stubs = stubs = [
            create_stub(addr, bind_stub, before_channel_created, after_channel_created)
            for _ in repeat(None, self.max_channels)
        ]
        for stub in stubs:
            stub.initialize(srv_name, srv_cls, self._circuit_breaker)

        # extra stub: dedicated to consumer coroutine
        stub = create_stub(addr, bind_stub, None, None)
        stub.initialize(srv_name, srv_cls, self._circuit_breaker)
        task = create_task(srv_cls.service_consumer(addr, stub))
        task.add_done_callback(lambda _: create_task(stub.close()))
        self.service_consumer_task = task

    def rebuild_if_needs(self):
        return super().rebuild_if_needs()

    async def close(self):
        task, self.service_consumer_task = self.service_consumer_task, None
        task.cancel()

        try:
            await task
        except CancelledError:
            pass
        except BaseException as exc:
            logger.exception(
                f"Found exc in GrpcService.service_consumer: %s", exc, exc_info=exc
            )

        stubs, self.stubs = self.stubs, None
        tasks = [create_task(stub.close()) for stub in stubs]
        await wait(tasks)


READY = "stub_repo_ready"
CLOSING = "stub_repo_closing"
CLOSED = "stub_repo_closed"


class GrpcStubRepositorty:
    pause_delay: int = 5
    __slots__ = (
        "state",
        "srv_name",
        "srv_cls",
        "services",
        "ring",
        "round_robin",
        "monitor_task",
        "force_check_waiter",
    )

    def __init__(self, srv_name: str, srv_cls: "GrpcService"):
        self.srv_name = srv_name
        self.srv_cls = srv_cls
        self.services: dict[ServiceAddr, GrpcStubGroup] = {}

        self.round_robin = RoundRobin()
        self.ring = HashRing(vnodes=100)

        self.force_check_waiter: Future
        self.monitor_task: Optional[Task] = None

        self.state = READY

    def add(
        self, addr: str, stub_group_cls: Union["GrpcStubGroup", "GrpcStubGroupWithTask"]
    ):
        if self.state is not READY:
            return

        logger.info(f"{self.srv_name} / {addr} needs to be added.")
        services = self.services
        if (stub_group := services.get(addr)) is not None:
            logger.warning(
                f"{self.srv_name} / {addr} already in repository, but received OnlineEvent"
            )
            state = stub_group.state
            state |= ChannelState.ETCD_REPORT_UP
            state &= ~ChannelState.ETCD_REPORT_DOWN
            stub_group.state = state
            return

        if self.monitor_task is None:
            self.force_check_waiter = Future()
            self.monitor_task = create_task(self.monitor())

        stub_group: GrpcStubGroup = stub_group_cls(addr)
        stub_group.state |= ChannelState.ETCD_REPORT_UP

        stub_group.initialize(self.srv_name, self.srv_cls)  # create_channel
        if stub_group.check_if_any_healthy():  # IDLE -> CONNECTING, READY LATER
            logger.info(f"{self.srv_name} / {addr} is up currently.")
            # stub_group.state = ChannelState.ALIVE
        else:  # grpc_channel_create is successful, but channel is not ready now.
            if not (waiter := self.force_check_waiter).done():  # wait to check
                waiter.set_result(None)
            stub_group.state |= ChannelState.SUBJECT_REBUILD
            logger.warning(
                f"connecting {self.srv_name} / {addr} now, ready to check its state later."
            )
        services[addr] = stub_group
        self.round_robin.add(stub_group)
        self.ring.add_node(addr)

    def remove(self, addr: str):
        if self.state is not READY:
            return

        logger.info(f"{self.srv_name} / {addr} needs to be removed.")
        services = self.services
        if (stub_group := services.get(addr)) is None:
            logger.warning(
                f"{self.srv_name} / {addr} not in repository, but received OfflineEvent"
            )
            return

        state = stub_group.state
        if state & ChannelState.SUBJECT_DOWN or not stub_group.check_if_any_healthy():
            logger.warning(f"{self.srv_name} / {addr} is down currently.")
            services.pop(addr)
            self.round_robin.remove(stub_group)
            self.ring.remove_node(addr)
            create_task(stub_group.close())
            return

        # otherwise REBUILD, check whether it's healthy or not.
        state &= ~ChannelState.ETCD_REPORT_UP
        state |= ChannelState.ETCD_REPORT_DOWN | ChannelState.SUBJECT_REBUILD
        if not (waiter := self.force_check_waiter).done():
            waiter.set_result(None)
        stub_group.state = state
        return

    def notify_connection_alive(self, stub_group: GrpcStubGroup):
        # found one READY stub, just mark it alive whether it is in REBUILD or not
        stub_group.state &= ~ChannelState.SUBJECT_DOWN

    def notify_connection_lost(self, stub_group: GrpcStubGroup):
        state = stub_group.state
        if state & ChannelState.SUBJECT_REBUILD:  # wait REBUILD completes
            return

        state |= ChannelState.SUBJECT_REBUILD  # double check later
        stub_group.state = state

        logger.warning(
            f"Found all channels in GrpcStubGroup<{self.srv_name}> lost: {stub_group.addr}"
        )
        if not (waiter := self.force_check_waiter).done():
            waiter.set_result(None)

    async def monitor(self):  # period: 60s
        def _awake_monitor():
            nonlocal timer
            if not force_check_waiter.done():
                self.round_robin.decay()
                force_check_waiter.set_result(None)
            timer = loop_call_later(60, _awake_monitor)

        async def _inner_impl():
            nonlocal force_check_waiter
            needs_pop = []
            pending_tasks = []
            # pending_groups = set()
            services = self.services
            round_robin, ring = self.round_robin, self.ring
            while True:
                await force_check_waiter
                for addr, stub_group in services.items():
                    stub_group.decay_rb()
                    if stub_group.state & ChannelState.SUBJECT_REBUILD:  # check again
                        if tasks := stub_group.rebuild_if_needs():  # wait connected
                            # pending_groups.add(stub_group)
                            pending_tasks.extend(tasks)
                            if len(tasks) < len(stub_group.stubs):  # alive
                                logger.info(
                                    f"{self.srv_name} / {addr} is partially READY now"
                                )
                                stub_group.state &= ~ChannelState.SUBJECT_DOWN
                        else:  # double check and find all channels are READY
                            logger.info(f"{self.srv_name} / {addr} is all READY now")
                            stub_group.state &= ~(
                                ChannelState.SUBJECT_REBUILD | ChannelState.SUBJECT_DOWN
                            )
                    elif not stub_group.check_if_any_healthy():  # CONNECTING or FAILED
                        if stub_group.is_down:
                            logger.warning(
                                f"{self.srv_name} / {addr} may be down currently"
                            )
                            needs_pop.append(addr)
                            # As pending_tasks stops the world, if service is online
                            # during this time, then this addr should not be removed
                            # so it's better to check again `is_down` property later
                        else:
                            stub_group.state &= ChannelState.SUBJECT_REBUILD
                    else:
                        stub_group.state &= ~ChannelState.SUBJECT_DOWN

                if pending_tasks:
                    # throw in CancelledError, then all pending_tasks will be cancelled later
                    await gather(
                        *pending_tasks, return_exceptions=True
                    )  # wait a moment
                    pending_tasks.clear()

                    # ReCheck
                    for addr, stub_group in services.items():
                        stub_group.state &= ~ChannelState.SUBJECT_REBUILD
                        if not stub_group.check_if_any_healthy():
                            stub_group.state |= ChannelState.SUBJECT_DOWN
                            if stub_group.state & ChannelState.ETCD_REPORT_DOWN:
                                logger.warning(
                                    f"{self.srv_name} / {addr} is down currently"
                                )
                                needs_pop.append(addr)
                        else:
                            logger.info(f"{self.srv_name} / {addr} is READY now")
                            stub_group.state &= ~ChannelState.SUBJECT_DOWN

                        if (linked_stubs := stub_group.linked_stubs) is not None:
                            siblings_stub_cls = self.srv_cls.__bind_stub__[1:]
                            for seq, stub in enumerate(stub_group.stubs):
                                if stub.is_new_one:
                                    for dest_stub_cls in siblings_stub_cls:
                                        channel = stub._channel
                                        stub = dest_stub_cls(channel)
                                        grpc_stub = GrpcStub(channel, stub)
                                        grpc_stub.initialize(
                                            self.srv_name,
                                            self.srv_cls,
                                            stub_group._circuit_breaker,
                                        )
                                        linked_stubs[dest_stub_cls.__name__][seq] = stub
                                    stub.is_new_one = False

                if needs_pop:
                    for addr in needs_pop:
                        stub_group = services.pop(addr)
                        if stub_group.is_down:  # Check again
                            round_robin.remove(stub_group)
                            ring.remove_node(addr)
                            create_task(stub_group.close())
                    needs_pop.clear()

                    # pending_groups.clear()
                self.force_check_waiter = force_check_waiter = Future()

        loop_call_later = get_running_loop().call_later
        # nonlocal variables
        force_check_waiter = self.force_check_waiter
        timer = loop_call_later(5, _awake_monitor)  # fast check

        pause_delay = self.pause_delay
        while True:
            try:
                await _inner_impl()
            except CancelledError:
                timer.cancel()
                break
            except BaseException as exc:
                logger.exception(
                    "Found exception in GrpcStubGroup.monitor: %s", exc, exc_info=exc
                )
                await sleep(pause_delay)

    async def close(self):
        self.state = CLOSING

        tasks = []
        if (task := self.monitor_task) is not None:
            self.monitor_task = None
            task.cancel()
            tasks.append(task)

        if services := self.services:
            self.services = None
            tasks.extend(
                create_task(stub_group.close()) for stub_group in services.values()
            )

        if tasks:
            await wait(tasks)

        self.state = CLOSED


class GrpcService:
    __bind_stub__: Optional[StubClassType | list[StubClassType]] = None
    __registry: dict[ServiceName, "GrpcService"] = dict()

    reuse = tuple()  # reuse raw definition
    wrapped_directly = tuple()  # with error handler
    wrapped_with_combination = tuple()  # request args combination and error handler
    customization = tuple()  # specific definition

    before_channel_created: Callable[[GrpcManager], Coroutine] = None
    after_channel_created: Callable[
        [StubClassType, GrpcManager],
        Coroutine,
    ] = None
    service_consumer: Callable = None

    services: defaultdict[ServiceName, GrpcStubRepositorty] = defaultdict(
        GrpcStubRepositorty
    )

    def __init_subclass__(cls) -> None:
        # service_name is the same as cls.__name__
        srv_name = cls.__name__
        if (bind_stub := cls.__bind_stub__) is None:
            raise Exception(
                f"There is a missing attribute `__bind_stub__` in class {srv_name},\n"
                "which name must be like 'UserStub', and this class has service methods"
                "like 'UserLogin', 'UserRegister' etc."
            )

        if not isinstance(bind_stub, type):
            if isinstance(bind_stub, (list, tuple)):
                for stub_cls in bind_stub:
                    if isinstance(stub_cls, type):
                        continue
                    else:
                        raise Exception(
                            f"UsageError: invalid StubClass: {stub_cls} in class {srv_name}"
                        )
            else:
                raise Exception(
                    f"UsageError: invalid `__bind_stub__` in class {srv_name}, "
                    "which should be one StubClassType or a list of it"
                )

        if meths := cls.customization:
            for meth_name in meths:
                meth = getattr(cls, meth_name, None)
                if meth is None:
                    raise Exception(f"{cls} doesn't implement {meth_name}")
                depend_stub = meth.__annotations__.get("depend_stub")
                if depend_stub is None:
                    if not isinstance(bind_stub, type):
                        raise Exception(f"{meth_name} missed `depend_stub` annotation")
                    meth.__annotations__["depend_stub"] = bind_stub
                elif not (depend_stub is bind_stub or depend_stub in bind_stub):
                    raise Exception(f"{meth_name} holds a wrong `depend_stub` type")

        GrpcService.__registry[srv_name] = cls
        services = GrpcService.services
        services[srv_name] = GrpcStubRepositorty(srv_name, cls)

    @classmethod
    def bind(cls, srv_name: str, srv_addr: str):
        if (repo := cls.services.get(srv_name)) is not None:
            srv_cls = cls.__registry[srv_name]
            repo.add(
                srv_addr,
                GrpcStubGroup
                if srv_cls.service_consumer is None
                else GrpcStubGroupWithTask,
            )

    @classmethod
    def unbind(cls, srv_name: str, srv_addr: str):
        if (repo := cls.services.get(srv_name)) is not None:
            repo.remove(srv_addr)

    @classmethod
    def inject(cls, grpc_manager):
        for srv_cls in cls.__registry.values():
            if (cb := srv_cls.before_channel_created) is not None:
                srv_cls.before_channel_created = partial(cb, grpc_manager)
            if (cb := srv_cls.after_channel_created) is not None:
                srv_cls.after_channel_created = partial(cb, grpc_manager=grpc_manager)

    @classmethod
    async def close(cls):
        for repository in cls.services.values():
            await repository.close()
