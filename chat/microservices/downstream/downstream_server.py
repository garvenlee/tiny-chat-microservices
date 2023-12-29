from chatp.starter import create_starter, move_on_starter
from chatp.entrypoint import AsyncMultiProcessManager
from factory import serve


should_exit = False


def handle_exit(*args, **kwargs) -> None:
    global should_exit
    should_exit = True


async def entrypoint(starter: AsyncMultiProcessManager):
    global should_exit
    from asyncio import sleep

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
        print("begin to shutdown...")


if __name__ == "__main__":
    import uvloop

    uvloop.install()
    # main_pid = os.getpid()
    # os.sched_setaffinity(main_pid, {4})  # mainprocess:0
    with create_starter(
        "./conf.yaml",
        worker_factory=serve,
        handle_exit=handle_exit,
    ) as starter:
        from asyncio import run as AsyncIORun

        AsyncIORun(entrypoint(starter))
