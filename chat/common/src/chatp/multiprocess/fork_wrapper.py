# from sys import stdout as sys_stdout
# from logging import getLogger
from functools import wraps
from time import sleep
from typing import Callable, Optional

from .worker import BaseWorkerProcess
from ..manager.loadbalance import LoadBalancer
from ..manager.grpc_client import GrpcClientManager
from ..rpc.grpc_service import GrpcService


def post_fork_wrapper(
    wrapped: Callable,
    *,
    post_fork: Callable,
    user_event_handler: Optional[Callable] = None,
):
    # logger = getLogger("ProcessManager")

    @wraps(wrapped)
    def wrapper(proc: BaseWorkerProcess):
        # must wait main process to initialize successfully
        shared_array = proc.proc_manager.shared_array
        while not shared_array[-1]:
            sleep(0.5)

        print(f"[WorkProcess] {proc.name} already started", flush=True)
        # sys_stdout.flush()
        if post_fork:
            post_fork(proc)  # tight arrange

        load_manager = LoadBalancer(GrpcService.services)
        grpc_manager = GrpcClientManager(
            multi_work_mode=True, bidirectional=proc.bidirectional
        )
        grpc_manager.post_initialize(
            proc,
            load_manager,
            user_handler=user_event_handler,
        )

        return wrapped(proc, grpc_manager)

    return wrapper
