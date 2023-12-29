import logging
from typing import AsyncContextManager
from functools import partial

from asyncio import Queue
from rstream import ConfirmationStatus

from utils.model import GrpcMessageWrapper
from chatp.rmq.stream.backend import RMQStreamBackend
from chatp.rmq.stream.producer import RMQStreamProducer


logger = logging.getLogger("RMQService")
logger.setLevel(10)


class RMQService(AsyncContextManager):
    backend: RMQStreamBackend
    producer: RMQStreamProducer
    ack_queue: Queue  # used to inform user

    def __init__(self, setting: dict) -> None:
        self.setting = setting

    def bind_queue(self, queue: Queue):
        self.ack_queue = queue

    def publish_confirm_cb(
        self, confirmation: ConfirmationStatus, message: GrpcMessageWrapper
    ):
        if confirmation.is_confirmed:
            self.ack_queue.put_nowait(message)
        else:
            # wait user to find timeout
            resp_code = confirmation.response_code
            logger.warning(f"Failed to Push: {resp_code}")

    async def __aenter__(self):
        def routing_extractor(wrapper: GrpcMessageWrapper):
            return str(wrapper.msg_data_wrapper.message.session_id)

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
        )
        self.producer = super_stream_producer

        self.publish_message = partial(
            super_stream_producer.send, on_publish_confirm=self.publish_confirm_cb
        )
        return self

    async def __aexit__(self, exc_tp, exc_val, exc_tb):
        await self.backend.__aexit__(exc_tp, exc_val, exc_tb)
