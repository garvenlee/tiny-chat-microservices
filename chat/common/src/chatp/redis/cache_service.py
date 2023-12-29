from logging import getLogger
from time import monotonic
from enum import IntEnum
from collections import deque
from typing import Optional, Callable, Any
from itertools import repeat, chain
from asyncio import (
    sleep,
    wait,
    wait_for,
    get_running_loop,
    Future,
    Queue,
    TimerHandle,
    TimeoutError,
    CancelledError,
)
from anyio import move_on_after
from aiomisc.circuit_breaker import CircuitBroken
from redis.asyncio import (
    ConnectionError as RedisConnectionError,
    TimeoutError as RedisTimeoutError,
)

from .model import *
from .handler import RedisHandlerMixin
from ..utils.circuit_breaker import CircuitBreakerMixin

logger = getLogger("redis_service")


class Resolution(IntEnum):
    SECOND = 1
    MINUTE = 60


class ConnectionState(IntEnum):
    WAIT_FOR_CONNECTED = 0
    CONNECTED = 1
    DISCONNECTED = 2
    CLOSING = 3
    CLOSED = 4


WAIT_FOR_CONNECTED = ConnectionState.WAIT_FOR_CONNECTED
CONNECTED = ConnectionState.CONNECTED
DISCONNECTED = ConnectionState.DISCONNECTED
CLOSING = ConnectionState.CLOSING
CLOSED = ConnectionState.CLOSED


class MonitorSpawnType(IntEnum):
    NO_WORKER = 0
    ONLY_READER = 1
    ONLY_WRITER = 2
    BOTH_WORKER = 3


ONLY_READER = MonitorSpawnType.ONLY_READER
ONLY_WRITER = MonitorSpawnType.ONLY_WRITER
BOTH_WORKER = MonitorSpawnType.BOTH_WORKER
NO_WORKER = MonitorSpawnType.NO_WORKER


class RedisCacheService(CircuitBreakerMixin, RedisHandlerMixin):
    READ_LIMIT: int = 1024
    WRITE_LIMIT: int = 1024

    RESERVE_CONNECTIONS: int = 3  # leftover
    RESERVE_EXECUTION_TIME: float = 0.05  # tolerate 50ms at most

    READER_RATIO: float = 0.3  # write operation is lower

    RESOLUTION = Resolution.SECOND

    exceptions = (RedisConnectionError, RedisTimeoutError)

    ERROR_RATIO: float = 0.2
    RESPONSE_TIME: int = 10
    PASSING_TIME: int = 3
    BROKEN_TIME: int = 5
    RECOVERY_TIME: int = 3

    def __init__(
        self,
        uri: str,
        *,
        max_connections: int,
        reserve_connections: Optional[int] = None,
        read_limit: Optional[int] = None,
        write_limit: Optional[int] = None,
        idle_timeout: int = 300,
        **kwargs,
    ) -> None:
        self.uri = uri

        cls = self.__class__

        self.max_connections = max_connections
        if reserve_connections is None:
            reserve_connections = cls.RESERVE_CONNECTIONS
        self.reserve_connections = reserve_connections

        if read_limit is None:
            read_limit = cls.READ_LIMIT
        if write_limit is None:
            write_limit = cls.WRITE_LIMIT

        self._read_limit = read_limit
        self._write_limit = write_limit

        kwargs_pop = kwargs.pop

        # CircuitBreaker config
        self.error_ratio = kwargs_pop("error_ratio", cls.ERROR_RATIO)
        self.response_time = kwargs_pop("response_time", cls.RESPONSE_TIME)
        self.passing_time = kwargs_pop("passing_time", cls.PASSING_TIME)
        self.broken_time = kwargs_pop("broken_time", cls.BROKEN_TIME)
        self.recovery_time = kwargs_pop("recovery_time", cls.RECOVERY_TIME)

        self._reader_ratio = kwargs_pop("reader_rate", cls.READER_RATIO)

        # Task
        self._readers: deque[TaskConsumer] = deque()
        self._writers: deque[TaskConsumer] = deque()
        self._idle_workers: set[TaskConsumer] = set()  # unused currently

        # Batch Collector
        # self._collector = GroupManager()

        # statistic info
        self._rw_ratio: float = 0
        self._time_span: float = 0
        self._idle_rebalance = True

        self.enqueue_block_count: int = 0
        self.timeout_count: int = 0

        self.read_count: int = 0
        self.write_count: int = 0
        self.total_read_delay: float = 0
        self.total_write_delay: float = 0
        self.average_read_delay: float = 0
        self.average_write_delay: float = 0

        self.idle_timeout: int = idle_timeout
        self.reserve_execution_time: float = kwargs_pop(
            "reserve_execution_time", cls.RESERVE_EXECUTION_TIME
        )

        self.state = WAIT_FOR_CONNECTED

    @property
    def total_connections(self):
        return self.max_connections + self.reserve_connections

    def reset(self):
        # the former statistic info as a whole batch
        average_read_delay = self.average_read_delay
        average_write_delay = self.average_write_delay

        self.read_count = int(average_read_delay > 0)
        self.write_count = int(average_write_delay > 0)
        self.total_read_delay = average_read_delay
        self.total_write_delay = average_write_delay

    async def redis_read(self, task_type: TaskStatus, argv: Any, timeout: float):
        if self.state >= CLOSING:
            return
        checkpoint = monotonic()

        task = RedisTask(task_type, argv, Future())
        await self._read_channel.put(task)

        timeout -= monotonic() - checkpoint
        if timeout > self.reserve_execution_time:  # 50ms default
            try:
                data = await wait_for(task.waiter, timeout=timeout)
            except TimeoutError:
                # self.read_count += 1
                self.timeout_count += 1
                raise
        else:
            self.enqueue_block_count += 1
            return

        delay = monotonic() - checkpoint
        self.read_count += 1
        self.total_read_delay += delay
        logger.info(f"{task_type.name} consumes {delay} s.")
        return data

    async def redis_write(self, task_type: TaskStatus, argv: Any, timeout: float):
        if self.state >= CLOSING:
            return
        checkpoint = monotonic()

        task = RedisTask(task_type, argv, Future())
        await self._write_channel.put(task)

        timeout -= monotonic() - checkpoint
        if timeout > self.reserve_execution_time:  # 50ms default
            try:
                data = await wait_for(task.waiter, timeout=timeout)
            except TimeoutError:
                # self.write_count += 1
                self.timeout_count += 1
                raise
        else:
            # self.write_count += 1
            self.enqueue_block_count += 1
            return

        delay = monotonic() - checkpoint
        self.write_count += 1
        self.total_write_delay += delay
        logger.info(f"{task_type.name} consumes {delay} s.")
        return data

    async def redis_read_batch(
        self,
        task_type: RedisTaskType,
        messages: list,
        timeout: float,
    ):
        num_batch = len(messages)
        if self.state >= CLOSING:
            return (None,) * num_batch

        if num_batch == 1:
            return (await self.redis_read(task_type, messages[0], timeout=timeout),)

        checkpoint = monotonic()
        batch = RedisBatchTask(RedisTaskType(task_type + 2), messages, Future())
        await self._read_channel.put(batch)

        timeout -= monotonic() - checkpoint
        if timeout > self.reserve_execution_time:  # 50ms default
            try:
                data = await wait_for(batch.waiter, timeout=timeout)
            except TimeoutError:
                # self.read_count += 1
                self.timeout_count += 1
                raise
        else:
            self.enqueue_block_count += 1
            return (None,) * num_batch

        delay = monotonic() - checkpoint
        self.read_count += 1
        self.total_read_delay += delay
        logger.info(f"{task_type.name} in batch({num_batch}) consumes {delay} s.")
        return data

    async def redis_write_batch(
        self,
        task_type: RedisTaskType,
        messages: list,
        futures: list[Future],
        timeout: float,
    ):
        if self.state >= CLOSING:
            for fut in futures:
                if not fut.done():
                    fut.set_result(None)
            return

        num_batch = len(messages)
        if num_batch == 1:
            try:
                fut = futures[0]
                data = await self.redis_write(task_type, messages[0], timeout=timeout)
            except TimeoutError as exc:
                if not fut.done():
                    fut.set_exception(exc)
            else:
                if not fut.done():
                    fut.set_result(data)
            return

        checkpoint = monotonic()
        batch = RedisBatchTask(RedisTaskType(task_type + 2), messages, Future())
        await self._write_channel.put(batch)

        timeout -= monotonic() - checkpoint
        if timeout > self.reserve_execution_time:  # 50ms default
            try:
                data = await wait_for(batch.waiter, timeout=timeout)
            except TimeoutError as exc:
                # self.write_count += 1
                self.timeout_count += 1
                for future in futures:
                    if not future.done():
                        future.set_exception(exc)
                return
        else:
            # self.write_count += 1
            self.enqueue_block_count += 1
            for future in futures:
                if not future.done():
                    future.set_result(None)
            return

        for future in futures:
            if not future.done():
                future.set_result(data)

        delay = monotonic() - checkpoint
        self.write_count += 1
        self.total_write_delay += delay
        logger.info(f"{task_type.name} in batch({num_batch}) consumes {delay} s.")

    def spawn_reader_task(self, num: int = 1):
        readers_append = self._readers.append
        reader_factory = self.reader
        task_factory = self._create_task
        idle_workers = self._idle_workers
        for _ in repeat(None, num):
            if not idle_workers:
                consumer = TaskConsumer()
            else:
                consumer = idle_workers.pop()
            consumer.task = task_factory(reader_factory(consumer))
            readers_append(consumer)
        logger.debug(f"[SpawnReaderTask] New {num} consumers.")

    def spawn_writer_task(self, num: int = 1):
        writers_append = self._writers.append
        writer_factory = self.writer
        task_factory = self._create_task
        idle_workers = self._idle_workers
        for _ in repeat(None, num):
            if not idle_workers:
                consumer = TaskConsumer()
            else:
                consumer = idle_workers.pop()
            consumer.task = task_factory(writer_factory(consumer))
            writers_append(consumer)
        logger.debug(f"[SpawnWriterTask] New {num} consumers.")

    async def check_health(self, retry=True) -> bool:  # check the RedisServer
        try:
            await self._backend.ping()
        except (RedisConnectionError, RedisTimeoutError):
            return await self.check_health(retry=False) if retry else False
        else:
            return True

    def cancel_timer(self, _: Future):
        if (handle := self._delay_calculator_handle) is not None:
            handle.cancel()
        if (handle := self._enqueue_checker_handle) is not None:
            handle.cancel()
        if (handle := self._delay_checker_handle) is not None:
            handle.cancel()
        if (handle := self._inactive_checker_handle) is not None:
            handle.cancel()

    def delay_calculator(
        self, call_later: Callable[[float, Callable, Any], TimerHandle], delay: float
    ):
        if write_count := self.write_count:
            self.average_write_delay = self.total_write_delay / write_count

        if read_count := self.read_count:
            cur_total_count = read_count + write_count
            self._rw_ratio = read_count / cur_total_count
            self.average_read_delay = self.total_read_delay / read_count

        self._delay_calculator_handle = call_later(
            delay, self.delay_calculator, call_later, delay
        )

    # grpc's concurrency is 4096, read + write tasks at most: 1024 + 1024
    def enqueue_checker(
        self,
        last_time_span: float,
        last_total_count: int,
        call_later: Callable[[float, Callable, Any], TimerHandle],
        delay: float,
    ):
        # TODO in order to cancel several consumers
        time_span = self._time_span
        logger.debug(f"[EnqueueChecker] Consumer time span: {time_span}")
        if time_span > last_time_span:
            pass

        read_count, write_count = self.read_count, self.write_count
        cur_total_count = read_count + write_count
        increment = cur_total_count - last_total_count

        block_count = self.enqueue_block_count
        timeout_count = self.timeout_count
        logger.debug(
            f"\t> blocked({block_count}) / timeout({timeout_count}) / "
            f"handled({increment}) totally in {delay}s window.\n"
            f"\t> read_count({read_count}) / write_count({write_count}): rw_ratio({self._rw_ratio}) currently."
        )
        self.enqueue_block_count = 0
        self.timeout_count = 0

        self._enqueue_checker_handle = call_later(
            delay, self.enqueue_checker, time_span, cur_total_count, call_later, delay
        )

    def maybe_rebalance(
        self,
        readers: deque[TaskConsumer],
        writers: deque[TaskConsumer],
        inc_read_count: int,
        inc_write_count: int,
        average_read_delay: float,
        average_write_delay: float,
        last_spawn_type: MonitorSpawnType,
    ):
        def rebalance_to_reader(fut: Future[TaskConsumer]):
            consumer = fut.result()
            if consumer.rebalance_trap:
                consumer.task = create_task(self.reader(consumer))
                consumer.status = TASK_READY  # no need to ping
                consumer.rebalance_trap = False

        def rebalance_to_writer(fut: Future[TaskConsumer]):
            consumer = fut.result()
            if consumer.rebalance_trap:
                consumer.task = create_task(self.writer(consumer))
                consumer.status = TASK_READY  # no need to ping
                consumer.rebalance_trap = False

        if average_read_delay and average_write_delay:
            if inc_read_count and inc_write_count:
                self._idle_rebalance = True
                read_ratio = inc_read_count / (inc_read_count + inc_write_count)
                read_ratio = read_ratio * 0.6 + self._rw_ratio * 0.4
            elif inc_read_count or inc_write_count or self._idle_rebalance:
                self._idle_rebalance = False
                read_ratio = self._rw_ratio
            else:
                return

            total_read_delay = read_ratio * average_read_delay
            total_write_delay = (1 - read_ratio) * average_write_delay
            read_delay_ratio = total_read_delay / (total_read_delay + total_write_delay)

            # TODO how to decides the num_readers_new
            num_readers, num_writers = len(readers), len(writers)
            cur_total_workers = num_readers + num_writers
            # reader_ratio = num_readers / cur_total_workers  # non-zero
            num_readers_new = int(read_delay_ratio * cur_total_workers)

            if (readers_need_inc := (num_readers_new - num_readers)) > 0:  # raise read
                if last_spawn_type & ONLY_WRITER:
                    num_writers_can_rebalance = (
                        num_writers // 4
                    )  # allow to decay 1/4 at most
                else:
                    num_writers_can_rebalance = (
                        num_writers - 2
                    )  # at least two writers available

                already_rebalance = 0
                if (availables := min(readers_need_inc, num_writers_can_rebalance)) > 0:
                    create_task = self._create_task
                    writers_pop, readers_append = writers.pop, readers.append
                    for _ in repeat(None, num_writers):
                        consumer = writers_pop()
                        # maybe dont exist this status, but in case
                        if (status := consumer.status) <= TASK_READY:
                            writers.appendleft(consumer)
                            continue
                        consumer.rebalance_trap = True
                        readers_append(consumer)
                        task = consumer.task
                        if status & TASK_IDLE:  # only IDLE or RUNNING
                            task.cancel()  # safe, because Queue.get will except
                        # consumer.status = TASK_READY
                        task.add_done_callback(rebalance_to_reader)

                        already_rebalance += 1
                        if already_rebalance == availables:
                            break

                if (readers_need_inc := (readers_need_inc - already_rebalance)) and (
                    availables := min(
                        self.total_connections - cur_total_workers, readers_need_inc
                    )
                ) > 0:
                    self.spawn_reader_task(availables)

                logger.debug(
                    f"[Rebalance] After: {num_readers} RedisReader(s), {num_writers} RedisWriter(s)."
                )

            elif readers_need_inc < 0:  # raise writer
                writers_need_inc = -readers_need_inc
                if last_spawn_type & ONLY_READER:
                    num_readers_can_rebalance = num_readers // 4
                else:
                    num_readers_can_rebalance = num_readers - 1

                already_rebalance = 0
                if (availables := min(writers_need_inc, num_readers_can_rebalance)) > 0:
                    create_task = self._create_task
                    readers_pop, writers_append = readers.pop, writers.append
                    for _ in repeat(None, num_readers):
                        consumer = readers_pop()
                        # maybe dont exist this status, but in case system is slow
                        if (status := consumer.status) <= TASK_READY:
                            readers.appendleft(consumer)
                            continue

                        consumer.rebalance_trap = True
                        writers_append(consumer)
                        task = consumer.task
                        if status & TASK_IDLE:
                            task.cancel()
                        task.add_done_callback(rebalance_to_writer)

                        already_rebalance += 1
                        if already_rebalance == availables:
                            break

                if (writers_need_inc := (writers_need_inc - already_rebalance)) and (
                    availables := min(
                        self.total_connections - cur_total_workers, writers_need_inc
                    )
                ) > 0:
                    self.spawn_writer_task(availables)

                logger.debug(
                    f"[Rebalance] After: {num_readers} RedisReader(s), {num_writers} RedisWriter(s)."
                )

    def delay_checker(
        self,
        readers: deque[TaskConsumer],
        writers: deque[TaskConsumer],
        reserve_execution_time: float,
        last_read_count: int,
        last_write_count: int,
        last_spawn_type: MonitorSpawnType,
        call_later: Callable[[float, Callable, Any], TimerHandle],
        delay: float,
    ):
        read_delay = self.average_read_delay
        write_delay = self.average_write_delay
        logger.debug(
            f"[DelayChecker] Average-Read-Delay({read_delay}), Average-Write-Delay({write_delay})."
        )

        read_count, write_count = self.read_count, self.write_count
        inc_read_count, inc_write_count = (
            read_count - last_read_count,
            write_count - last_write_count,
        )

        self.maybe_rebalance(
            readers,
            writers,
            inc_read_count,
            inc_write_count,
            read_delay,
            write_delay,
            last_spawn_type,
        )

        num_readers, num_writers = len(readers), len(writers)
        used = num_readers + num_writers
        availables = 2 * self.total_connections - used  # 2 times
        if availables:
            if (
                read_delay >= reserve_execution_time
                and write_delay > reserve_execution_time
            ):
                num_new_reader = int(availables * self._reader_ratio)
                self.spawn_reader_task(min(num_new_reader, max(num_readers // 2, 1)))
                self.spawn_writer_task(
                    min(availables - num_new_reader, max(num_writers // 2, 1))
                )
                delay = 1
                last_spawn_type = BOTH_WORKER
            elif read_delay >= reserve_execution_time:
                if not (last_spawn_type & ONLY_READER):
                    self.spawn_reader_task(
                        max(
                            min(int(availables * self._reader_ratio), num_readers // 2),
                            1,
                        )
                    )
                    delay = 1  # TODO delay check
                    last_spawn_type = ONLY_READER
                elif inc_read_count > 10:  # still delay
                    self.spawn_reader_task(
                        max(
                            int(availables * self._reader_ratio),
                            1,  # at least 1
                        )
                    )
                    delay = 0.5  # TODO delay check
                    last_spawn_type = ONLY_READER
            elif write_delay >= reserve_execution_time:
                if not (last_spawn_type & ONLY_WRITER):  # the first raise
                    self.spawn_writer_task(
                        max(
                            min(
                                int(availables * (1 - self._reader_ratio)),
                                num_writers // 2,
                            ),
                            1,  # at least 1
                        )
                    )
                    delay = 1  # TODO delay check
                    last_spawn_type = ONLY_WRITER
                elif inc_write_count > 10:  # still delay
                    self.spawn_writer_task(
                        max(
                            int(availables * (1 - self._reader_ratio)),
                            1,  # at least 1
                        )
                    )
                    delay = 0.5  # TODO delay check
                    last_spawn_type = ONLY_WRITER
            else:
                delay = 5
                last_spawn_type = NO_WORKER

        self._delay_checker_handle = call_later(
            delay,
            self.delay_checker,
            readers,
            writers,
            reserve_execution_time,
            read_count,
            write_count,
            last_spawn_type,
            call_later,
            delay,
        )

    def inactive_checker(
        self,
        readers: deque[TaskConsumer],
        writers: deque[TaskConsumer],
        call_later: Callable[[float, Callable, Any], TimerHandle],
        idle_timeout: int,
    ):
        # check inactivate task
        checkpoint = monotonic()
        inactive_count = 0

        # idle_workers = self._idle_workers
        # idle_workers_add = idle_workers.add
        logger.debug(
            f"[InactiveChecker], readers({len(readers)}), writers({len(writers)}) / "
            f"read_count({self.read_count}) write_count({self.write_count}) in {idle_timeout}s window."
        )
        # keypoint: update task.last_state as soon as there is a item to be executed
        readers_append, readers_popleft = readers.append, readers.popleft
        for _ in repeat(None, len(readers)):
            consumer = readers_popleft()
            if checkpoint - consumer.last_state > idle_timeout:
                # now this task needs to cancel
                # consumer.task.cancel()  # cancelled safe?
                # idle_workers_add(consumer)
                inactive_count += 1
                readers_append(consumer)
            else:
                readers_append(consumer)

        if inactive_count:  # dont cancel
            logger.debug(f"\t> RedisReader: Found {inactive_count} in LONG IDLE.")
            inactive_count = 0

        writers_append, writers_popleft = writers.append, writers.popleft
        for _ in repeat(None, len(writers)):
            consumer = writers_popleft()
            if checkpoint - consumer.last_state > idle_timeout:
                # now this task needs to cancel
                # consumer.task.cancel()
                # idle_workers_add(consumer)
                inactive_count += 1
                writers_append(consumer)
            else:
                writers_append(consumer)

        if inactive_count:  # dont cancel
            logger.debug(f"\t> RedisWriter: Found {inactive_count} in LONG IDLE.")
            inactive_count = 0

        self.reset()
        self._inactive_checker_handle = call_later(
            idle_timeout,
            self.inactive_checker,
            readers,
            writers,
            call_later,
            idle_timeout,
        )

    async def monitor(self):
        readers: deque[TaskConsumer] = self._readers
        writers: deque[TaskConsumer] = self._writers
        idle_timeout = self.idle_timeout
        call_later = self._loop.call_later
        reserve_execution_time = self.reserve_execution_time

        # delay calculate / 50ms: average_delay & _rw_ratio
        self._delay_calculator_handle = call_later(
            0.05, self.delay_calculator, call_later, 0.05
        )
        # block_count & timeout_count / 1s
        self._enqueue_checker_handle = call_later(
            1, self.enqueue_checker, 0, 0, call_later, 1
        )
        # rebalance & new consumers / 5s
        self._delay_checker_handle = call_later(
            5,
            self.delay_checker,
            readers,
            writers,
            reserve_execution_time,
            0,
            0,
            NO_WORKER,
            call_later,
            5,
        )
        # idle checker & batch delay statistic info / 300s(default)
        self._inactive_checker_handle = call_later(
            idle_timeout,
            self.inactive_checker,
            readers,
            writers,
            call_later,
            idle_timeout,
        )

        check_health = self.check_health
        while True:
            await sleep(5)  # maybe dynamic
            if await check_health(retry=True):
                self.state = CONNECTED
            else:  # TODO PING failed, IO error, use Redis Sentinel
                logger.error("Bad: IO Error")
                self.state = DISCONNECTED

    async def rollback(self, consumer: TaskConsumer):
        if consumer.status is TASK_INITIALIZED:
            consumer.status = TASK_READY
            if await self.check_health(retry=False):
                # ready to get tasks as soon as possible
                logger.info("[RedisRollback] New Rollback pings successfully.")
            else:
                logger.warning("[RedisRollback] New Rollback failed to ping.")

        def count_logger(call_later):
            nonlocal count_logger_handle, count
            if count:
                logger.warning(
                    f"[RedisRollback] Currently totally {count} rollback operations."
                )

            count = 0
            count_logger_handle = call_later(5, count_logger, call_later)

        count = 0
        call_later = self._loop.call_later
        count_logger_handle = call_later(5, count_logger, call_later)

        rollback_channel = self._rollback_channel
        circuit_breaker_context = self._circuit_breaker.context
        while self.state is not CLOSING:  # TODO when get item, but server disconnected?
            try:
                consumer.status = TASK_IDLE
                coro_func, data = await rollback_channel.get()
                consumer.status = TASK_RUNNING

                count += 1
                with circuit_breaker_context():
                    await coro_func(*data)
            except CircuitBroken as exc:
                logger.warning(f"CircuitBreaker catched error: {exc}")
            except CancelledError:
                break
            except BaseException as exc:
                logger.error(
                    f"Found exception in Rollback<{coro_func.__name__}>: {exc}"
                )

        count_logger_handle.cancel()
        while not rollback_channel.empty():
            try:
                coro_func, data = rollback_channel.get_nowait()
                await coro_func(*data)
            except CancelledError:
                logger.warning(
                    f"[RedisService] RollbackQueue still has {len(rollback_channel)} items"
                )
                break
            except BaseException as exc:
                logger.warning(
                    f"Found exception in Rollback<{coro_func.__name__}>: {exc}"
                )

    async def reader(self, consumer: TaskConsumer):
        if consumer.status is TASK_INITIALIZED:
            consumer.status = TASK_READY
            if await self.check_health(retry=False):
                # ready to get tasks as soon as possible
                logger.info("[RedisReader] New Reader pings successfully.")
            else:
                logger.warning("[RedisReader] New Reader failed to ping.")

        handlers = self._handlers
        circuit_breaker_context = self._circuit_breaker.context

        read_channel = self._read_channel
        while self.state is not CLOSING and not consumer.rebalance_trap:
            try:
                consumer.status = TASK_IDLE
                task = await read_channel.get()  # cancelled safe? may callback trigger
                if (waiter := task.waiter).done():
                    continue
                consumer.status = TASK_RUNNING

                checkpoint = monotonic()
                self._time_span = checkpoint - consumer.last_state
                consumer.last_state = checkpoint  # execution point

                waiter = task.waiter
                task_type = task.task_type
                with circuit_breaker_context():
                    executor, _ = handlers[task_type]
                    result = await executor(*task.task_data)  # at most 3s
                    if not waiter.done():
                        waiter.set_result(result)

            except CircuitBroken as exc:
                logger.warning(f"CircuitBreaker catched exception: {exc}")
                if not waiter.done():
                    waiter.set_result(None)
            except CancelledError:
                if consumer.rebalance_trap:
                    break

                if self.state is not CLOSING:
                    logger.warning("RedisReader was cancelled for long idle time.")
                    break
                else:
                    logger.info("RedisReader was cancelled for server closed.")

                while not read_channel.empty():
                    task = read_channel.get_nowait()
                    if (waiter := task.waiter).done():
                        continue

                    executor, _ = handlers[task.task_type]
                    try:
                        result = await executor(*task.task_data)  # at most 1s
                        if not waiter.done():
                            waiter.set_result(result)
                    except BaseException:
                        if not waiter.done():
                            waiter.set_result(None)
                break
            except BaseException as exc:
                logger.error(f"Found exception in RedisTask<{task_type.name}>: {exc}")
                if not waiter.done():
                    waiter.set_result(None)

        return consumer

    async def writer(self, consumer: TaskConsumer):
        if consumer.status is TASK_INITIALIZED:
            consumer.status = TASK_READY
            if await self.check_health(retry=False):
                # ready to get tasks as soon as possible
                logger.info("[RedisWriter] New Writer pings successfully.")
            else:
                logger.warning("[RedisWriter] New Writer failed to ping.")

        rollback = None
        handlers = self._handlers
        circuit_breaker_context = self._circuit_breaker.context

        rollback_channel = self._rollback_channel
        write_channel = self._write_channel
        while self.state is not CLOSING and not consumer.rebalance_trap:
            try:
                consumer.status = TASK_IDLE
                task = await write_channel.get()
                if (waiter := task.waiter).done():
                    continue
                consumer.status = TASK_RUNNING

                checkpoint = monotonic()
                self._time_span = checkpoint - consumer.last_state
                consumer.last_state = checkpoint  # execution point

                task_type = task.task_type
                task_data = task.task_data
                with circuit_breaker_context():
                    executor, rollback = handlers[task_type]
                    result = await executor(*task_data)
                    if not waiter.done():
                        waiter.set_result(result)
                    elif rollback is not None:  # this will cause inconsistency
                        rollback_channel.put_nowait((rollback, task_data))
                        rollback = None

            except CircuitBroken as exc:
                logger.warning(f"CircuitBreaker catched exception: {exc}")
                if not waiter.done():
                    waiter.set_result(None)
            except CancelledError:
                if consumer.rebalance_trap:
                    break

                if self.state is not CLOSING:
                    # Actually, not necessary, Task needs smaller cost than process
                    logger.warning("RedisWriter was cancelled for long idle time.")
                    break
                else:
                    logger.info("RedisWriter was cancelled for server closed.")

                if rollback is not None:
                    rollback_channel.put_nowait((rollback, task_data))

                while not write_channel.empty():
                    task = write_channel.get_nowait()
                    if (waiter := task.waiter).done():
                        continue

                    executor, rollback = handlers[task.task_type]
                    try:
                        result = await executor(*task.task_data)  # at most 1s
                    except BaseException:
                        if not waiter.done():
                            waiter.set_result(None)
                    else:
                        if not waiter.done():
                            waiter.set_result(result)
                        elif rollback is not None:  # TODO check this
                            rollback_channel.put_nowait((rollback, task_data))

                break
            except BaseException as exc:
                logger.error(f"Found exception in RedisTask<{task_type.name}>: {exc}")
                if not waiter.done():
                    waiter.set_result(None)

        return consumer

    async def __aenter__(self) -> None:
        logger.info("begin to start redis_service...")

        self.cb_initialize(
            error_ratio=self.error_ratio,
            response_time=self.response_time,
            passing_time=self.passing_time,
            broken_time=self.broken_time,
            recovery_time=self.recovery_time,
        )
        # TODO add RTQ args, st. prefix,
        await self.handler_initialize(
            uri=self.uri,
            total_connections=2 * self.total_connections + 2,  # ping & rollback
        )

        logger.info("redis_service is active!")

        # Group Initialize
        # collector = self._collector
        # for task_type in self._handlers:
        #     collector.register(task_type)

        self._loop = loop = get_running_loop()
        self._read_channel: Queue[RedisTask] = Queue(maxsize=self._read_limit)
        self._write_channel: Queue[RedisTask] = Queue(maxsize=self._write_limit)
        self._rollback_channel: Queue[RedisTask] = Queue(maxsize=self._write_limit)

        self._create_task = create_task = loop.create_task

        totals = self.max_connections
        num = int(totals * self._reader_ratio)
        self.spawn_reader_task(min(num, 1))
        self.spawn_writer_task(min(totals - num, 2))

        rollback_consumer = TaskConsumer()
        rollback_task = create_task(
            self.rollback(rollback_consumer), name="RedisCacheService.rollback"
        )
        rollback_consumer.task = rollback_task
        self._rollback_consumer = rollback_consumer

        self._monitor_task = create_task(
            self.monitor(), name="RedisCacheService.monitor"
        )
        self._monitor_task.add_done_callback(self.cancel_timer)
        return self

    async def __aexit__(self, exc_tp, exc_val, exc_tb) -> None:
        self.state = CLOSING
        monitor_task, self._monitor_task = self._monitor_task, None
        monitor_task.cancel()

        readers, writers = self._readers, self._writers
        self._readers = self._writers = None
        self._read_channel = self._write_channel = None

        cancelled = [monitor_task]
        for consumer in chain(readers, writers):
            if consumer.status & TASK_READY:  # READY or IDLE
                task = consumer.task
                task.cancel()  # maybe not safe
                cancelled.append(task)

        logger.info(f"Begin to cancel running [{len(cancelled)}] workers...")
        with move_on_after(5) as scope:
            await wait(cancelled)

        if scope.cancel_called:
            logger.warning("[RedisService] Cancel READY Tasks took too long")

        self._rollback_channel = None
        rollback_consumer, self._rollback_consumer = self._rollback_consumer, None
        rollback_task = rollback_consumer.task
        if rollback_consumer.status & TASK_READY:  # READY or IDLE
            rollback_task.cancel()

        with move_on_after(15) as scope:
            await rollback_task  # wait all task done

        if scope.cancel_called:
            logger.warning(
                "[RedisService] Cannot wait RedisRollbackTask to be done anymore"
            )

        await self._backend.close(close_connection_pool=True)
        self.state = CLOSED
        logger.info("RedisService has been closed safely")