from signal import signal, SIGINT, SIGTERM
from asyncio import BaseEventLoop, get_running_loop
from threading import current_thread, main_thread
from typing import Callable, Optional


HANDLED_SIGNALS = (
    SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)


def install_signal_handlers(
    handler: Callable, loop: Optional[BaseEventLoop] = None
) -> None:
    if current_thread() is not main_thread():
        # Signals can only be listened to from the main thread.
        return

    if loop is None:
        loop = get_running_loop()
    try:
        for sig in HANDLED_SIGNALS:
            loop.add_signal_handler(sig, handler, sig, None)
    except NotImplementedError:  # pragma: no cover
        # Windows
        for sig in HANDLED_SIGNALS:
            signal(sig, handler)
