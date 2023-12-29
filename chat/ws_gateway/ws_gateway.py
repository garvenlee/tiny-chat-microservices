from types import FrameType
from typing import Optional

from asyncio import sleep, run as AsyncIORun

from creator import post_fork, create_worker
from chatp.starter import create_starter, move_on_starter
from chatp.entrypoint import AsyncMultiProcessManager


should_exit = False


# sig: int, frame: Optional[FrameType]
def handle_exit(*args, **kwargs) -> None:
    global should_exit
    should_exit = True


async def entrypoint(starter: AsyncMultiProcessManager):
    async with move_on_starter(starter):
        # mainloop - statistic
        if starter.use_monitor:
            console_locals = starter.console_locals
            console_locals["cycle"] = 0

            counter = 0
            while not should_exit:
                counter += 1
                last_counter = counter
                counter = counter % 864000

                console_locals["tic-toc"] = counter  # unit: 0.1s
                if last_counter > counter:
                    console_locals["cycle"] += 1
                await sleep(0.1)
        else:
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
        # os.sched_setaffinity(main_pid, {0})  # mainprocess:0

        print(f"> Started parent process [{main_pid}] at {datetime.now()}\n")
        AsyncIORun(entrypoint(starter))
        print(f"\n> Stopping parent process [{main_pid}] at {datetime.now()}")
