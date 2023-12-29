from types import FrameType
from typing import Optional
from asyncio import run as AsyncIORun, sleep

from creator import create_worker, post_fork
from chatp.starter import create_starter, move_on_starter
from chatp.entrypoint import AsyncMultiProcessManager

should_exit = False


# sig: int, frame: Optional[FrameType]
def handle_exit(*args, **kwargs) -> None:
    global should_exit
    should_exit = True


async def entrypoint(starter: AsyncMultiProcessManager):
    global should_exit

    async with move_on_starter(starter):
        # mainloop - statistic
        counter = 0
        while not should_exit:
            counter += 1
            counter = counter % 864000
            await sleep(0.1)


if __name__ == "__main__":
    import uvloop

    uvloop.install()
    with create_starter(
        "./conf.yaml",
        worker_factory=create_worker,
        post_fork=post_fork,
        handle_exit=handle_exit,
    ) as starter:
        import os
        from datetime import datetime

        main_pid = os.getpid()
        # os.sched_setaffinity(main_pid, {6})  # mainprocess:0

        print(f"> Started parent process [{main_pid}] at {datetime.now()}\n")
        AsyncIORun(entrypoint(starter))
        print(f"\n> Stopping parent process [{main_pid}] at {datetime.now()}")
