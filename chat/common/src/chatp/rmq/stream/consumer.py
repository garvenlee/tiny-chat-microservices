from logging import getLogger
from time import monotonic
from functools import partial
from typing import Any, Awaitable, Optional, Callable
from contextlib import suppress
from inspect import iscoroutinefunction

from asyncio import (
    CancelledError,
    Task,
    get_running_loop,
    create_task,
    sleep,
    wait,
    # shield,
)
from rstream.amqp import AMQPMessage
from rstream.exceptions import OffsetNotFound
from rstream.constants import ConsumerOffsetSpecification, OffsetType
from rstream.consumer import EventContext, MessageContext, OffsetSpecification
from rstream.superstream import DefaultSuperstreamMetadata
from rstream.superstream_consumer import SuperStreamConsumer, CB, MT

from .model import OffsetRecord, StreamMessage


logger = getLogger("RabbitConsumer")


class RMQStreamConsumer(SuperStreamConsumer):
    offset_maintenance_task: Task

    OFFSET_STORE_FORCE_PER_MESSAGES: int = 256
    OFFSET_STORE_MINIMUM_MESSAGES: int = 64
    OFFSET_STORE_PERIOD: int = 300  # 5min

    def __init__(
        self,
        host: str,
        port: int = 5552,
        *,
        username: str,
        password: str,
        super_stream: str,
        consumer_group_name: str,
        connection_closed_handler: Optional[CB[Exception]] = None,
        **extra,
    ):
        super().__init__(
            host,
            port,
            username=username,
            password=password,
            super_stream=super_stream,
            connection_closed_handler=connection_closed_handler,
            **extra,
        )

        self.consumer_group_name = consumer_group_name
        # subscriber_name : OffsetRecord[stream, offset]
        self.offset_recorder: dict[str, OffsetRecord] = {}

    async def startup(self):
        await self.start()
        await self.initialize_consumer()
        self.offset_maintenance_task = create_task(self.store_offset_timer())

    async def close(self):
        if (task := self.offset_maintenance_task) is not None and not task.done():
            self.offset_maintenance_task = None
            with suppress(CancelledError):
                task.cancel()
                await task

        await super().close()

    async def start(self):
        self._default_client = await self._pool.get(
            connection_name="rstream-locator",
            connection_closed_handler=self._connection_closed_handler,
        )
        self._super_stream_metadata = DefaultSuperstreamMetadata(
            self.super_stream, self._default_client
        )

    # TODO Currently, each stream queue, one consumer(one subscriber, two conns)
    async def initialize_consumer(self):
        recorder = self.offset_recorder
        consumers = self._consumers
        partitions = await self._super_stream_metadata.partitions()
        subscriber_name_suffix = f"_subscriber_{self.consumer_group_name}"
        for partition in partitions:
            consumers[partition] = await self._create_consumer()
            recorder[f"{partition}{subscriber_name_suffix}"] = OffsetRecord(
                partition, -1  # expected_offset is 0, last_stored_offset is -1
            )

    async def store_offset_timer(self):
        def on_store_offset(task: Task, *, record: OffsetRecord, offset: int):
            if record.storing_offset == offset:
                record.storing_offset = -1
                if not task.cancelled():
                    if (exc := task.exception()) is None:
                        record.last_stored_offset = offset
                        record.last_stored_time = monotonic()
                    else:
                        logger.exception(
                            "Found exc in `store_offset`: %s", exc, exc_info=exc
                        )
            else:
                logger.warning(
                    f"StoreOffset routine found the subscriber in {record.stream} became inactive"
                )

        FORCE_THRESOLD = self.OFFSET_STORE_FORCE_PER_MESSAGES
        MIN_THRESOLD = self.OFFSET_STORE_MINIMUM_MESSAGES
        STORE_PERIOD = self.OFFSET_STORE_PERIOD
        consumers, recorder = self._consumers, self.offset_recorder

        tasks = []
        tasks_append, tasks_clear = tasks.append, tasks.clear
        loop_create_task = get_running_loop().create_task
        try:
            while True:
                await sleep(10)  # TODO check delay time

                curr_time = monotonic()
                for subscribe_name, record in recorder.items():
                    if record.frozen:
                        continue

                    curr_max_offset = record.expected_offset - 1
                    num_handled = curr_max_offset - record.last_stored_offset
                    if num_handled > FORCE_THRESOLD or (
                        num_handled > MIN_THRESOLD
                        and curr_time > record.last_stored_time + STORE_PERIOD  # 5min
                    ):
                        partition = record.stream
                        task = loop_create_task(
                            consumers[partition].store_offset(
                                partition, subscribe_name, curr_max_offset
                            )
                        )
                        task.add_done_callback(
                            partial(
                                on_store_offset, record=record, offset=curr_max_offset
                            )
                        )
                        tasks_append(task)

                        record.storing_offset = curr_max_offset

                if tasks:
                    await wait(tasks)
                    tasks_clear()
        except CancelledError:
            if tasks:
                await wait(tasks)

    async def subscribe_cb_wrapper(
        self,
        message: AMQPMessage,
        message_context: MessageContext,
        user_cb: Callable[[StreamMessage], Awaitable[None] | None],
    ):
        subscriber_name = message_context.subscriber_name
        record = self.offset_recorder[subscriber_name]
        if record.frozen:  # fast shield TODO Later Check if rstream adds Flow Control
            return

        try:
            stream_message = StreamMessage(message, message_context, record)
            if iscoroutinefunction(user_cb):
                await user_cb(stream_message)  # create_task? must check message.active
            else:
                user_cb(stream_message)
        except BaseException as exc:
            logger.exception(
                "Found exc in user consumer: %s, lost one message: stream/%s, offset/%s",
                exc,
                record.stream,
                message_context.offset,
                exc_info=exc,
            )

    async def consumer_update_listener(
        self, is_active: bool, event_context: EventContext
    ):
        subscriber_name = event_context.subscriber_name
        record = self.offset_recorder[subscriber_name]
        stream = record.stream
        # stream = event_context.consumer.get_stream(subscriber_name)
        if is_active:
            try:
                offset = await self._consumers[stream].query_offset(
                    stream, subscriber_name
                )
            except OffsetNotFound:
                logger.info(
                    f"For {stream}, {subscriber_name} becomes active, with expected_offset: 0"
                )
                record.unfreeze()
                return OffsetSpecification(OffsetType.OFFSET, 0)
            except BaseException as exc:
                logger.warning(
                    "Panic: current active consumer is replaying all messages in %s",
                    stream,
                )
                record.unfreeze()
                return OffsetSpecification(OffsetType.OFFSET, 0)
            else:
                record.unfreeze()  # make sure the state is brand new
                record.add(offset)  # the first offset, expected_offset is right
                record.last_stored_offset = offset
                next_offset = offset + 1
                logger.info(
                    f"For {stream}, {subscriber_name} becomes active, with expected_offset: {next_offset}"
                )
                return OffsetSpecification(OffsetType.OFFSET, next_offset)

        else:
            expected_offset = record.expected_offset
            last_stored_offset = record.last_stored_offset
            logger.info(
                f"For {stream}, {subscriber_name} becomes inactive, with expected_offset: {expected_offset}, last_stored_offset: {last_stored_offset}"
            )

            # freeze first - shield any change from async-tasks
            record.freeze()  # also clear queue
            # attempt store here - TODO maybe use redis as external storage to set state
            if record.is_storing_offset:
                logger.warning("Found another inflight `store_offset`: %s", stream)

            if (
                last_stored_offset < (pending_stored_offset := expected_offset - 1)
                and record.storing_offset < pending_stored_offset
            ):
                logger.info(
                    "Found offset has been updated since last store in %s, decided to store offset anyway",
                    stream,
                )
                record.storing_offset = pending_stored_offset
                try:
                    await self._consumers[stream].store_offset(
                        stream, subscriber_name, pending_stored_offset
                    )
                    record.last_stored_offset = pending_stored_offset
                    record.last_stored_time = monotonic()
                except BaseException as exc:
                    logger.exception(
                        "Found exception in `store_offset` when subscriber became inactive: %s",
                        exc,
                        exc_info=exc,
                    )
                finally:
                    record.storing_offset = -1
            # server will ignore this
            return OffsetSpecification(OffsetType.OFFSET, expected_offset)

    async def subscribe(
        self,
        callback: Callable[[StreamMessage], Awaitable[None] | None],
        *,
        decoder: Callable[[bytes], MT] | None = None,
        initial_credit: int = 10,
        properties: dict[str, Any] | None = None,
        consumer_update_listener: Callable[[bool, EventContext], Awaitable[Any]]
        | None = None,
    ):
        callback_wrapper = partial(self.subscribe_cb_wrapper, user_cb=callback)
        if consumer_update_listener is None:
            consumer_update_listener = self.consumer_update_listener

        subscriber_name_suffix = f"_subscriber_{self.consumer_group_name}"
        offset_recorder = self.offset_recorder
        for partition, consumer in self._consumers.items():
            subscriber_name = f"{partition}{subscriber_name_suffix}"
            offset = offset_recorder[subscriber_name].expected_offset
            subscriber = await consumer.subscribe(
                stream=partition,
                callback=callback_wrapper,
                decoder=decoder,
                offset_specification=ConsumerOffsetSpecification(
                    OffsetType.OFFSET,
                    offset,
                ),
                initial_credit=initial_credit,
                properties=properties,
                subscriber_name=subscriber_name,
                consumer_update_listener=consumer_update_listener,
            )
            self._subscribers[partition] = subscriber


class RbflyStreamConsumer:
    pass
