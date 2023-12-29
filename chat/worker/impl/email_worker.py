from typing import Optional
from functools import partial
from asyncio import CancelledError, Event, wait, get_running_loop

from async_sender import Mail
from aiosmtplib.errors import SMTPDataError
from aio_pika.message import IncomingMessage

from chatp.rmq.pika.backend import RMQBackend
from chatp.rmq.pika.consumer import RMQConsumer
from chatp.rmq.pika.model import ConsumerMessage
from chatp.proto.services.mail.email_pb2 import email as EmailMessage

from .base_worker import RMQWorker
from utils.log import set_default_logger

set_default_logger("RMQWorker")


class EmailWorker(RMQWorker):
    backend: RMQBackend

    async def initialize(self):
        setting = self.setting
        consumer_factory = self.backend.create_consumer(
            exchange_type=setting["EMAIL_EXCHANGE_TYPE"],
            exchange_name=setting["EMAIL_EXCHANGE_NAME"],
            routing_key=setting["EMAIL_ROUTING_KEY"],
            queue_name=setting["EMAIL_QUEUE_NAME"],
        )
        create_task = get_running_loop().create_task
        tasks = [create_task(consumer_factory(initial_qos=10))]  # one consumer
        await wait(tasks)
        self.consumers = [task.result() for task in tasks]
        self.logger.info("RMQ Service connected.")

        self.sender = Mail(
            hostname=setting["EMAIL_HOST_NAME"],
            port=setting["EMAIL_PORT"],
            username=setting["EMAIL_USERNAMAE"],
            password=setting["EMAIL_PASSWORD"],
            from_address=setting["EMAIL_FROM_ADDRESS"],
        )
        self.shutdown_event = Event()

    async def handler(self, consumer: RMQConsumer):
        shutdown = False
        last_seen_message: Optional[IncomingMessage] = None

        def on_consume(pika_message: IncomingMessage):
            nonlocal last_seen_message
            if shutdown:
                last_seen_message = pika_message
                return

            message = ConsumerMessage(pika_message)
            if not self.validate_source(pika_message):
                task = create_task(self.discard_message(message))
                task.add_done_callback(tasks.discard)
                tasks.add(task)
                return

            logger.info("Received one message, ready to send email...")
            self.total_count += 1

            task = create_task(email_handler(message))
            task.add_done_callback(tasks.discard)
            tasks.add(task)

        tasks = set()
        create_task = get_running_loop().create_task

        logger = self.logger
        email_handler = partial(self.email_handler, sender=self.sender)
        async with consumer.start_listen(on_consume, lambda: last_seen_message):
            try:
                await self.shutdown_event.wait()
            except CancelledError:
                logger.info(
                    "handler is cancelled, now need to wait inflight tasks done..."
                )
                # TODO move read_queue.cancel here, so there will not be fast-discard messages
                # then these messages can be handled by other node faster
                shutdown = True
                if tasks:
                    await wait(tasks)

    async def email_handler(self, message: ConsumerMessage, *, sender: Mail):
        email = EmailMessage.FromString(message._message.body)
        email_html = email.template.format(link=email.link)
        try:
            to_user = email.to_addr
            await sender.send_message(
                "Register Confirmation",
                to=to_user,
                html=email_html,
            )
        except SMTPDataError as exc:
            self.logger.exception(
                f"Found an Invalid email to {to_user}: %s", exc, exc_info=exc
            )
            self.failed_count += 1
            await message.reject(requeue=False)  # cannot be consumed again
        except CancelledError:
            await message.reject()
        except BaseException as exc:  # TODO corner check
            self.logger.exception("Found unexpected exception: %s", exc, exc_info=exc)
            self.failed_count += 1
            await message.reject(requeue=False)
        else:
            self.logger.info(f"Send one email to {to_user} successfully")
            self.succeed_count += 1
            await message.ack()
