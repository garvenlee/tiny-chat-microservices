from enum import IntEnum
from types import FrameType
from typing import List, Dict, Optional
from itertools import repeat

from asyncio import (
    Future,
    Task,
    BaseEventLoop,
    CancelledError,
    StreamReader,
    get_event_loop,
    sleep,
)

from network.tasks import TaskManager
from sessions.manager import SessionManager
from models.websocket import WsAppEvent, KICKED_OFF
from models.chat import PendingLogType
from utils.terminal import clear_before_exit, switch_to_new_page

from base.app import BaseApp
from base.page import BasePage, Quit, Back
from base.status_bar import StatusBar, NotificationType
from ui.chat_session_page import ChatSessionPage, format_new_message

from chatp.utils.signals import install_signal_handlers


class AppState(IntEnum):
    READY = 0
    ACTIVE = 1
    CLOSING = 2
    CLOSED = 3


# manage different pages' info, including history messages
class ChatApp(BaseApp):
    def __init__(self, loop: Optional[BaseEventLoop] = None):
        self._stack: List[BasePage] = []
        self.routes: Dict[str, "BasePage"]

        self.state: AppState = AppState.READY

        self.current_page: Optional[BasePage] = None
        self.ui_task: Optional[Task] = None
        self.control_task: Optional[Task] = None

        if loop is None:
            loop = get_event_loop()
        self._loop = loop

        self.ws_event: Optional[WsAppEvent] = None
        self.status_bar = StatusBar(loop=loop)

    def bind(self, routes: Dict[str, "BasePage"]):
        self.routes = routes
        for page in routes.values():
            page.bind(self)

    def handle_exit(self, sig: int, frame: Optional[FrameType]):
        self.control_task.cancel()
        clear_before_exit()

    def notify(self, event: WsAppEvent, **extra_info):
        self.ws_event = event

        status_bar = self.status_bar
        match event:
            case WsAppEvent.INBOUND_MESSAGE:
                curr_page = self.current_page
                sender_id, local_id = extra_info["sender_id"], extra_info["local_id"]
                if isinstance(curr_page, ChatSessionPage):
                    chat_session = curr_page.session
                    if chat_session.friend_id == sender_id:  # in current page
                        curr_page.bubble_message(local_id)
                    else:  # TODO Add Notification MessageGroup
                        message = chat_session.messages_timeline[local_id]
                        status_bar.show_notification_in_duration(
                            format_new_message(
                                chat_session.friend_header, message.text, overflow=15
                            )
                        )
                else:
                    chat_session = self.active_user_session.chat_sessions[sender_id]
                    message = chat_session.messages_timeline[local_id]
                    status_bar.show_notification_in_duration(
                        format_new_message(
                            chat_session.friend_header, message.text, overflow=15
                        )
                    )

            case WsAppEvent.INBOUND_ACKED_MESSAGE:
                curr_page = self.current_page
                receiver_id, local_id = (
                    extra_info["receiver_id"],
                    extra_info["local_id"],
                )
                if (
                    isinstance(curr_page, ChatSessionPage)
                    and curr_page.session.friend_id == receiver_id
                ):
                    if curr_page.session.timeout_ids:
                        curr_page.on_message_sent_success(local_id)
                else:
                    # before rendering the page, check the pending_operations
                    chat_session = self.active_user_session.chat_sessions[receiver_id]
                    chat_session.append_log(local_id, log_tp=PendingLogType.SENT_ACKED)
                status_bar.show_notification_in_duration("sent message success")

            case WsAppEvent.OUTBOUND_MESSAGE_TIMEOUT:
                curr_page = self.current_page
                receiver_id, local_id = (
                    extra_info["receiver_id"],
                    extra_info["local_id"],
                )
                if (
                    isinstance(curr_page, ChatSessionPage)
                    and curr_page.session.friend_id == receiver_id
                ):
                    curr_page.on_message_sent_timeout(local_id)
                else:
                    # before rendering the page, check the pending_operations
                    chat_session = self.active_user_session.chat_sessions[receiver_id]
                    if local_id not in chat_session.timeout_ids:
                        chat_session.append_log(
                            local_id, log_tp=PendingLogType.SENT_TIMEOUT
                        )
                status_bar.show_notification_in_duration(
                    "sent message timeout", tp=NotificationType.WARNING
                )

            case WsAppEvent.KICKED_OFF:
                status_bar.show_notification_in_duration(
                    extra_info["text"], NotificationType.WARNING
                )
                self.control_task.cancel()
            case _:
                pass

    async def initialize(self, **connection_args):
        task_manager = TaskManager(self._loop)

        self._task_manager = task_manager
        self.create_task = task_manager.create_task
        self.create_timer = task_manager.create_timer

        session_manager = SessionManager(**connection_args)
        self._session_manager = session_manager
        self.create_user_session = session_manager.create_user_session
        self.activate_user_session = session_manager.activate_user_session
        self.create_chat_session = session_manager.create_chat_session
        self.activate_chat_session = session_manager.activate_chat_session

        self.state_check = session_manager.state_check

        install_signal_handlers(self.handle_exit, loop=self._loop)

        # # from opentelemetry.exporter.jaeger.proto.grpc import JaegerExporter
        # from opentelemetry.sdk.resources import Resource
        # from opentelemetry.semconv.resource import ResourceAttributes
        # from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        # from chatp.utils.uuid import generate
        # from chatp.utils.telemetry import Telemetry
        # # opentelemetry intialize
        # resource = Resource.create(
        #     {
        #         ResourceAttributes.SERVICE_NAMESPACE: "ChatApp",
        #         ResourceAttributes.SERVICE_NAME: "TerminalClient",
        #         ResourceAttributes.SERVICE_VERSION: "v1.0.0",
        #         ResourceAttributes.SERVICE_INSTANCE_ID: generate(),
        #         ResourceAttributes.OS_NAME: "Ubuntu 22.04",
        #     }
        # )
        # exporter = JaegerExporter(collector_endpoint="localhost:14250", insecure=True)
        # Telemetry().setup_telemetry_tracer_provider(
        #     resource, exporter
        # )  # needs closed when lifespan shutdown

        # HTTPXClientInstrumentor().instrument()

    @property
    def active_user_session(self):
        return self._session_manager._active_user_session

    @property
    def active_chat_session(self):
        return self._session_manager._active_chat_session

    async def close(self):
        await self._task_manager.close()

        for page in self._stack:
            page.store.clear()
        self._stack.clear()

    async def ui_loop(self, reader: StreamReader):
        stack = self._stack
        stack.append(self.routes["entry_page"])
        stack_pop = stack.pop

        task_factory = self._loop.create_task
        self.state = AppState.ACTIVE
        status_bar = self.status_bar
        while True:
            try:
                while stack:
                    if self.ui_task is None:
                        # 1.clear page content & move to bottom lineo
                        switch_to_new_page()

                        tail = stack[-1]
                        self.current_page = tail

                        # 2.render status_bar
                        # TODO optimize, only update page_field
                        status_bar.set_page_name(tail.name)
                        status_bar.render()

                        # 3.render page content
                        tail.render()

                    self.ui_task = task_factory(tail.interaction(reader))
                    next_page = await self.ui_task
                    if next_page is Quit:
                        clear_before_exit()
                        return
                    elif next_page is Back:
                        stack_pop()
                    else:
                        stack.append(next_page)

                    self.ui_task = None

            except CancelledError:
                ws_event = self.ws_event
                if ws_event is KICKED_OFF:
                    self.ws_event = None
                    self.ui_task.cancel()
                    self.ui_task = None
                    for _ in repeat(None, len(stack) - 1):
                        stack_pop().store.restore()

                    await sleep(3)
                else:  # exit this app
                    self.state = AppState.CLOSING
                    self.ui_task.cancel()
                    self.ui_task = None
                    break

    async def run(self, reader: StreamReader):
        def ui_task_cb(_: Future):
            if not waiter.done():
                waiter.set_result(False)

        if not self.routes:
            raise Exception(
                "you must bind this app with some routes before app runs.\n"
                "routes is a dict, like entry_page: EntryPage"
            )

        self.control_task = task = self._loop.create_task(self.ui_loop(reader))
        task.add_done_callback(ui_task_cb)

        waiter = Future()
        await waiter
        await self.close()
        self.state = AppState.CLOSED
        print("exit, bye!")
