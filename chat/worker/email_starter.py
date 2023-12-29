from types import FrameType
from typing import Optional
from asyncio import (
    Future,
    run,
    get_running_loop,
)

from chatp.utils.signals import install_signal_handlers

from impl.email_worker import EmailWorker


async def main():
    loop = get_running_loop()
    loop.set_debug(True)

    def handle_exit(sig: int, frame: Optional[FrameType]):
        print("> Catched a SIGINT signal from os kernel")
        nonlocal waiter
        if not waiter.done():
            waiter.set_result(None)

    install_signal_handlers(handle_exit, loop)

    from yaml import safe_load

    with open("./confs/email.yaml", "r", encoding="utf8") as fs:
        data = safe_load(fs)
        app_setting = data["app_setting"]
        del data

    async with EmailWorker(app_setting):
        waiter = Future()
        await waiter


if __name__ == "__main__":
    import uvloop

    uvloop.install()
    run(main())
