from sys import stdout
from time import monotonic
from logging import getLogger
from enum import IntEnum
from typing import (
    NamedTuple,
    AsyncIterator,
    Callable,
    Coroutine,
    Optional,
    Iterable,
)
from functools import partial
from collections import OrderedDict

from attrs import define
from aiomisc.service import Service
from aiomisc.backoff import asyncretry
from asyncio import (
    get_running_loop,
    wait,
    wait_for,
    shield,
    sleep,
    timeout as async_timeout,
    Event as AsyncIOEvent,
    Task,
    TaskGroup,
    CancelledError,
    TimeoutError as AsyncIOTimeoutError,
)
from anyio import move_on_after
from aetcd.client import Client
from aetcd.rtypes import GetRange, Event, EventKind, Watch
from aetcd.exceptions import ConnectionFailedError, ConnectionTimeoutError, ClientError

from ..discovery.etcd import RLease
from ..utils.types import ServiceAddr, PlatformId
from ..proto.processes.event_pb2 import (
    Event as ProcEvent,
    ServiceEvent,
    SERVICE_CHANGE,
    SERVICE_ONLINE,
    SERVICE_OFFLINE,
)


logger = getLogger("ServiceManager")
logger.setLevel(10)


class ETCDConnectionState(IntEnum):
    READY = 0
    CONNECTED = 1
    LOST = 2
    CLOSING = 3
    CLOSED = 4


@define(slots=True)
class Watcher:
    srv_name: str
    watch: Watch
    consumer: Task


class ServiceInfoItem(NamedTuple):
    addr: ServiceAddr
    platform_id: PlatformId


class ServiceManager(Service):
    registered_service_prefix: str
    discovered_service_prefix: str
    include_services: set

    connect_timeout: int = 5
    request_timeout: int = 5
    reconnect_timeout: int = 8

    max_retries: int = 3
    pause_delay: int = 5
    hibernate_time: int = 15

    monitor_task: Task  # only with ETCD_CONNECTED

    is_single: bool = False
    registered: bool = False
    watching: bool = False
    watchers: Optional[dict[str, Watcher]] = None

    retry = asyncretry(3, exceptions=(ConnectionTimeoutError,), pause=1)

    def __init_subclass__(cls) -> None:
        cls_include_services = cls.include_services
        if not isinstance(cls_include_services, Iterable):
            raise Exception(
                f"{cls.__name__} must bind `include_services`, which is a iterable object."
            )
        if cls_include_services and not isinstance(cls_include_services, set):
            cls.include_services = set(cls_include_services)

    def __init__(
        self,
        platform_id: str,
        service_name: str,
        service_addr: Optional[str] = None,
        etcd_host: str = "localhost",
        etcd_port: int = 2379,
        lease_ttl: int = 10,  # lease_ttl = 2 * request_timeout
    ):
        self.service_name = service_name
        self.platform_id = platform_id

        self_cls = self.__class__

        connect_kwargs = {
            "host": etcd_host,
            "port": etcd_port,
            "timeout": self_cls.request_timeout,
            "connect_wait_timeout": self_cls.connect_timeout,
        }
        self.connect_kwargs = connect_kwargs
        self._client = client = Client(**connect_kwargs)
        self._lease = RLease(lease_ttl, client)

        if registered_srv_prefix := self_cls.registered_service_prefix:
            self.use_registered = True
            self._etcd_registered_service_key = (
                f"{registered_srv_prefix}{platform_id}".encode("ascii")
            )
            self._etcd_registered_service_addr = service_addr.encode("ascii")
        else:
            self.use_registered = False

        if self_cls.include_services:
            self.use_discovery = True
            self._etcd_discovered_service_prefix = (
                self_cls.discovered_service_prefix.encode("ascii")
            )
            # in-memory cache with key `srv_name/platform_id` -> OrderedDict
            # `srv_name` -> [(srv_addr, srv_platform_id)]
            self._cache: OrderedDict[str, ServiceInfoItem] = OrderedDict()
            # self._cache: defaultdict[str, set[ServiceInfoItem]] = defaultdict(set)
        else:
            self.use_discovery = False

        self.orphan_clients: set[Client] = set()
        self.started_event = AsyncIOEvent()
        self.state = ETCDConnectionState.READY

    @property
    def lease_ttl(self):
        return self._lease.ttl

    @property
    def client(self):
        return self._client

    @property
    def cache(self):
        return self.__dict__.get("_cache")

    @property
    def health(self):
        return self.state is ETCDConnectionState.CONNECTED

    def bind(self, dispatch_event: Callable[[ProcEvent], Coroutine]):
        self.dispatch_event = dispatch_event

    async def connect(self, client: Client, *, timeout: Optional[int] = None):
        async with async_timeout(timeout):
            await client.connect()
            await client.channel.channel_ready()

            self.state = ETCDConnectionState.CONNECTED

    async def reconnect(self):
        client = self.client

        try:
            found_exc = False
            # First, Check the underlaying channel - move_on_after & scope.cancel_called
            with move_on_after(self.connect_timeout) as scope:
                await client.channel.channel_ready()  # try_to_connect, may reuse it
        except CancelledError:  # outer threw CancelledError into here
            raise
        except BaseException as exc:  # channel_ready raise exc, channel is not reusable
            logger.exception(
                "Found exception in `channel_ready`: %s", exc, exc_info=exc
            )
            found_exc = True

        # Second, if underlaying channel is still not READY, then close it and new one
        if found_exc or scope.cancel_called:  # new client
            try:
                await wait_for(shield(client.close()), timeout=5)
            except AsyncIOTimeoutError:
                self.orphan_clients.add(client)
                self.client = client = Client(**self.connect_kwargs)
            except CancelledError:
                raise
            except BaseException as exc:
                logger.exception(
                    "Unknown exception in aetcd.Client.close: %s", exc, exc_info=exc
                )
                self.orphan_clients.add(client)  # TODO Check
                self.client = client = Client(**self.connect_kwargs)

            await self.connect(client, timeout=self.__class__.reconnect_timeout)
            return True

        return False

    async def start_service_registry(self, key: bytes, val: bytes):
        lease_id = await self._lease.keepalive()
        # await self._client.put(key, val, lease_id)
        await self._client.put(key, val)
        self.registered = True
        return lease_id

    async def exit_service_registry(self, key: bytes):
        try:
            await self._lease.clear()  # s.t. requestsed lease not found
        except ClientError as exc:
            logger.exception(
                "Found ClientError in exit_service_registry: %s", exc, exc_info=exc
            )
        except BaseException as exc:
            logger.exception(
                "Found uncaught exception in exit_service_registry: %s",
                exc,
                exc_info=exc,
            )
        finally:
            self.registered = False
            # await self._client.delete(key)  # lease is revoked, key will be deleted then
            logger.info(f"Already deleted etcd_key: {key}")
            stdout.flush()

    async def start_service_discovery(self):
        include_services = self.__class__.include_services
        services_prefix = self._etcd_discovered_service_prefix
        prefix_len = len(services_prefix)
        client_get_prefix = self._client.get_prefix

        # Gather: if any task failed firstly, exc will be propagated to outer immediately,
        # then any other task' exc is only raised in its done_cb.
        # But, its sematic doesn't cancel other inflight task -> TaskGroup.
        # Only when outer called cancel, then all tasks would be cancelled !!!
        # Wait: outer called cancel, but don't cancel its tasks !!!
        async with TaskGroup() as tg:  # s.t. ConnectionTimeoutError
            create_task = tg.create_task
            tasks: list[Task[GetRange]] = [
                create_task(
                    client_get_prefix(services_prefix + bytes(srv_name, "ascii"))
                )
                for srv_name in include_services
            ]

        results = [task.result() for task in tasks]
        platform_id, cache = self.platform_id, self._cache
        dispatch_event = self.dispatch_event
        for srv_name, services_info in zip(include_services, results):
            srv_prefix_len = prefix_len + len(srv_name) + 1
            for kv in services_info:
                srv_platform_id = kv.key[srv_prefix_len:].decode("ascii")
                if (
                    srv_platform_id != platform_id
                    and (cache_key := f"{srv_name}/{srv_platform_id}") not in cache
                ):
                    srv_addr = kv.value.decode("ascii")
                    await dispatch_event(
                        ProcEvent(
                            evt_tp=SERVICE_CHANGE,
                            srv_evt=ServiceEvent(
                                srv_tp=SERVICE_ONLINE,
                                srv_name=srv_name,
                                srv_addr=srv_addr,
                                platform_id=srv_platform_id,
                            ),
                        )
                    )
                    cache[cache_key] = ServiceInfoItem(srv_addr, srv_platform_id)

    async def watch_services(self):
        services_prefix = self._etcd_discovered_service_prefix

        async def start_listen(srv_name: str) -> tuple[str, Watch]:
            srv_prefix = services_prefix + bytes(srv_name, "ascii")
            watch = await self._client.watch_prefix(srv_prefix)
            return srv_name, watch

        async def on_consume(srv_name: str, watch: AsyncIterator[Event]):
            srv_prefix_len = len(services_prefix) + len(srv_name) + 1
            platform_id, cache = self.platform_id, self._cache
            dispatch_event = self.dispatch_event
            async for event in watch:  # wait event from watch_prefix.locals.<event_queue>
                kv = event.kv
                srv_platform_id = kv.key[srv_prefix_len:].decode("ascii")
                if srv_platform_id != platform_id:
                    cache_key = f"{srv_name}/{srv_platform_id}"
                    if (kind := event.kind) == PUT:
                        if cache_key not in cache:
                            srv_addr = kv.value.decode("ascii")
                            logger.info(
                                f"[MainService] Ready to add one service: {srv_name}/{srv_addr}"
                            )
                            await dispatch_event(
                                ProcEvent(
                                    evt_tp=SERVICE_CHANGE,
                                    srv_evt=ServiceEvent(
                                        srv_tp=SERVICE_ONLINE,
                                        srv_name=srv_name,
                                        srv_addr=srv_addr,
                                        platform_id=srv_platform_id,
                                    ),
                                )
                            )
                            cache[cache_key] = ServiceInfoItem(
                                srv_addr, srv_platform_id
                            )
                    elif kind == DELETE:
                        item = cache.pop(cache_key, None)
                        if item is not None:
                            srv_addr = item.addr
                            logger.info(
                                f"[MainService] Ready to delete one service: {srv_name}/{srv_addr}"
                            )

                            await dispatch_event(
                                ProcEvent(
                                    evt_tp=SERVICE_CHANGE,
                                    srv_evt=ServiceEvent(
                                        srv_tp=SERVICE_OFFLINE,
                                        srv_name=srv_name,
                                        srv_addr=srv_addr,
                                        platform_id=srv_platform_id,
                                    ),
                                )
                            )
                    else:
                        # never comes here
                        pass

        def stream_cb(task: Task, *, srv_name: str):
            if task.cancelled():
                logger.warning(f"WatchStream is cancelled: {srv_name}")
            elif (exc := task.exception()) is None:
                logger.info(f"WatchStream is closed safely: {srv_name}")
            else:
                logger.exception(
                    f"WatchStream raise exception: {srv_name} / %s", exc, exc_info=exc
                )

        # await aiterator.cancel()  # client._watcher.cancel

        PUT, DELETE = EventKind.PUT, EventKind.DELETE
        async with TaskGroup() as tg:  # s.t. ConnectionTimeoutError
            create_task = tg.create_task
            listen_tasks = [
                create_task(start_listen(srv_name))
                for srv_name in self.__class__.include_services
            ]

        watchers = {}
        create_task = get_running_loop().create_task
        for task in listen_tasks:
            srv_name, watch = task.result()
            consumer = create_task(on_consume(srv_name, watch))
            consumer.add_done_callback(partial(stream_cb, srv_name=srv_name))
            watchers[srv_name] = Watcher(srv_name, watch, consumer)

        self.watchers = watchers
        self.watching = True

    async def kill_watchers(self, watchers: dict[str, Watcher]):
        tasks: list[Task] = []
        create_task = get_running_loop().create_task
        for watcher in watchers.values():
            watch, consumer = watcher.watch, watcher.consumer
            if not consumer.done():  # TODO Corner Check in reconnect
                # 1.exhaust the async iterator in consumer task, make it done normally
                # 2.enqueue one cancel message, underline rpc stream will send it out later
                tasks.append(create_task(watch.cancel()))

        if tasks:
            time_remaining = self.__class__.request_timeout
            with move_on_after(time_remaining) as scope:
                await wait(tasks)

            # here, wait at least one request_timeout until all inflight requests sent out
            # before closing the client
            if not scope.cancel_called:
                await sleep(scope.deadline - monotonic())
            else:
                for task in tasks:
                    if not task.done():
                        task.cancel()

            self.watching = False
            return True

        self.watching = False
        return False

    async def monitor(self):
        await self.started_event.wait()

        period = self.lease_ttl
        lease = self._lease if self.registered else None

        needs_pop = []
        orphan_clients = self.orphan_clients

        async def _inner_impl():
            is_lost = force_reconnect = False
            watchers = self.watchers

            while True:
                if orphan_clients:
                    logger.warning(f"Found {len(orphan_clients)} orphan clients")
                    for orphan_client in orphan_clients:
                        if not orphan_client._connected.is_set():
                            needs_pop.append(orphan_client)

                    if needs_pop:  # TODO Check garbage
                        for orphan_client in needs_pop:
                            orphan_clients.pop(orphan_client)
                        needs_pop.clear()

                if (
                    lease is not None
                    and (refresh_task := lease.refresh_task).done()
                    and (exc := refresh_task.exception()) is not None
                ):
                    # monitor_task.cancel() is called before "exit_service_registry"
                    # so it's safe to get exception directly
                    # s.t. ConnectionTimeoutError
                    logger.exception(
                        "lease expired due to %s, needs to rebuild later...",
                        exc,
                        exc_info=exc,
                    )
                    if isinstance(exc, ConnectionTimeoutError):
                        try:
                            # register myself again
                            await self.__class__.retry(self.start_service_registry)(
                                self._etcd_registered_service_key,
                                self._etcd_registered_service_addr,
                            )
                        except ClientError as exc:
                            self.state = ETCDConnectionState.LOST
                            force_reconnect = True
                            logger.exception(
                                "[Monitor] ServiceRegister failed again due to %s",
                                exc,
                                exc_info=exc,
                            )
                        except CancelledError:
                            raise
                        except BaseException as exc:
                            self.state = ETCDConnectionState.LOST
                            force_reconnect = True
                            logger.exception(
                                "[Monitor] Unknown exception in ServiceRegister: %s",
                                exc,
                                exc_info=exc,
                            )
                    elif isinstance(exc, ConnectionFailedError):  # maybe reconnect
                        self.state = ETCDConnectionState.LOST
                        force_reconnect = True
                        logger.exception(
                            "[Monitor] Found ETCD Server is down !!!", exc_info=exc
                        )
                    else:  # maybe requested lease not found
                        self.state = ETCDConnectionState.LOST
                        force_reconnect = True
                        logger.exception(
                            "[Monitor] Unexpected exception: %s", exc, exc_info=exc
                        )

                if watchers is not None:  # monitor the WatchStream
                    if not force_reconnect:
                        for watcher in watchers.values():
                            consumer = watcher.consumer
                            # check whether underlaying channel is lost
                            if (
                                consumer.done()
                                and (exc := consumer.exception()) is not None
                            ):
                                logger.exception(
                                    "WatchStream is lost, needs to rebuild later...",
                                    exc_info=exc,
                                )

                                is_lost = True
                                await self.kill_watchers(watchers)
                                watchers.clear()  # explicitly collect
                                break
                    else:
                        is_lost = True
                        await self.kill_watchers(watchers)

                # must rebuild the underline channel
                if is_lost or force_reconnect:  # exc will be captured outside
                    await self.reconnect()  # TODO ReCheck: without timeout
                    if force_reconnect:  # maybe raise ConnectionTimeoutError
                        await self.start_service_registry(
                            self._etcd_registered_service_key,
                            self._etcd_registered_service_addr,
                        )
                        force_reconnect = False

                    if is_lost:  # maybe raise ConnectionTimeoutError
                        self._cache.clear()
                        await self.watch_services()  # here, new watchers
                        watchers = self.watchers
                        is_lost = False

                    logger.info(
                        "Already rebuilt ETCDClient and service-related routine"
                    )
                await sleep(period)

        retries = max_retries = self.max_retries
        pause_delay = self.pause_delay
        hibernate_time = self.hibernate_time
        while True:
            try:
                await _inner_impl()
            except CancelledError:
                break
            except ClientError as exc:
                logger.exception(
                    "[Monitor] Found ClientError in the inner loop: %s",
                    exc,
                    exc_info=exc,
                )
                await sleep(pause_delay)
            except BaseException as exc:
                logger.exception(
                    "[Monitor] Found unknown exception in the inner loop: %s",
                    exc,
                    exc_info=exc,
                )
                await sleep(pause_delay)

            retries -= 1
            if retries == 0:
                logger.warning("EtcdService is in hibernate mode now")
                await sleep(hibernate_time)
                retries = max_retries

    # TODO Add ETCD Connection Monitor
    # currently just one connection, if network partition?
    async def start(self):
        use_registered, use_discovery = self.use_registered, self.use_discovery
        if use_registered or use_discovery:
            await self.connect(self._client, timeout=self.__class__.connect_timeout)
            self.monitor_task = get_running_loop().create_task(self.monitor())
            logger.info("Already connected to ETCD")
            stdout.flush()

            # service registry - RLease maintains keepalive task
            if use_registered:
                await self.start_service_registry(
                    self._etcd_registered_service_key,
                    self._etcd_registered_service_addr,
                )
                # self.registered = True
                logger.info(f"Already register {self.service_name} service")
                stdout.flush()

            # service discovery - firstly crawlers all services at this point and notifys them to workers
            if use_discovery:
                logger.info("Started to discover downstream microservices...")
                stdout.flush()
                await self.start_service_discovery()

                # watch services
                await self.watch_services()  # if raise exc, then `stop` will be called in entrypoint
                # self.watching = True
                logger.info("Now watching services...")
                stdout.flush()

            self.started_event.set()

    async def stop(self, exc):
        match self.state:
            case ETCDConnectionState.CONNECTED | ETCDConnectionState.LOST:
                self.state = ETCDConnectionState.CLOSING
                try:
                    task, self.monitor_task = self.monitor_task, None
                    if not task.done():
                        task.cancel()  # before `lease.clear`

                    if self.watching:  # safely exit before `client.close`
                        logger.info("Begin to kill all watchers")
                        await self.kill_watchers(self.watchers)
                        # self.watching = False

                    if self.registered:
                        logger.info("Begin to clear service registry")
                        # timeout? wait `client.close` to shutdown watcher
                        await self.exit_service_registry(
                            self._etcd_registered_service_key
                        )
                        # self.registered = False

                finally:
                    # TODO Check, directly teriminate the stream, leave the clear routine to ETCD Server
                    await self._client.close()
                    logger.info("Already stopped services in ServiceManager")
                    self.state is ETCDConnectionState.CLOSED

            case _:
                logger.info(
                    "ETCDConnectionState is %s, directly exit.",
                    self.state.name,
                )
