from concurrent.futures import ThreadPoolExecutor


def cpu_initializer():
    from os import getpid, sched_getaffinity, sched_setaffinity

    pid = getpid()
    cpu = sched_getaffinity(pid)
    print(f"{pid} process, cpu affinity {cpu}")  # 0 2 4 6
    sched_setaffinity(0, {5, 7})


def executor_shutdown(executor: ThreadPoolExecutor):
    executor.shutdown(wait=True)
