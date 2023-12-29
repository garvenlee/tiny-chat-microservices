from struct import pack
from typing import Callable, Any
from collections import defaultdict, OrderedDict

from aiomisc.service import Service
from asyncio import (
    Queue,
    TimerHandle,
    create_task,
    wait,
    get_running_loop,
)

from ..proto.processes.event_pb2 import (
    Event as ProcEvent,
    ServiceEvent,
    LoadHintEvent,
    LOAD_HINT,
)
from ..proto.processes.statistic_pb2 import LoadInfo, LoadItem
from ..multiprocess.worker import WorkerProcess
from ..multiprocess.base import DIRTY, DONE


class UsagePair:
    __slots__ = ("count", "proportion")

    def __init__(self):
        self.count = self.proportion = 0


class ServiceUsage:
    __slots__ = ("total_count", "usages")

    def __init__(self):
        self.total_count = 0
        self.usages = defaultdict(UsagePair)  # process_seq : count

    def update(self, proc_seq: int, count: int):
        self.total_count += count
        usage_pair = self.usages[proc_seq]
        usage_pair.count += count
        usage_pair.proportion = usage_pair.count / self.total_count

    def pop(self, proc_seq: int):
        usages = self.usages
        pair = usages.pop(proc_seq)
        self.total_count -= pair.count
        total = self.total_count
        for usage in usages.values():
            usage.proportion = usage.count / total


class StatisticManager(Service):
    work_mode: bool
    use_discovery: bool

    def __init__(self):
        self.name_map_usages: defaultdict[str, ServiceUsage] = defaultdict(ServiceUsage)
        self._proc_usages = {}

    def bind_queue(self, queue: Queue):
        self._proc_recv_queue = queue

    def bind_workers(self, workers: OrderedDict[int, WorkerProcess]):
        self._workers = workers  # feed_data about load info on all worker processes

    async def extract_info_single_mode(self, queue: Queue[ProcEvent]):
        # name_map_usages, proc_usages = self.name_map_usages, self._proc_usages
        # while True:
        #     event: ProcEvent = await queue.get()
        #     srv_evt: ServiceEvent = event.srv_evt
        #     name_map_usages[f"{srv_evt.srv_name}/{srv_evt.srv_addr}"].update(
        #         proc_seq, item.usage_count
        #     )
        pass

    async def extract_info_multi_mode(self, queue: Queue):
        name_map_usages, proc_usages = self.name_map_usages, self._proc_usages
        while True:
            data: bytes = await queue.get()
            info = LoadInfo.FromString(data)
            proc_seq = info.proc_seq
            proc_usages[proc_seq] = info.total_count
            for item in info.loads:
                name_map_usages[f"{info.srv_name}/{item.srv_addr}"].update(
                    proc_seq, item.usage_count
                )

    def proc_consistency(
        self,
        processes: OrderedDict[int, WorkerProcess],
        name_map_usages: defaultdict[str, ServiceUsage],
        proc_usages: dict,
        call_later: Callable[[float, Callable, Any], TimerHandle],
        delay: float,
    ):
        for proc in filter(lambda proc: proc.state is DIRTY, processes.values()):
            proc.state = DONE

            proc_seq = proc.process_seq
            # if not set d=None, maybe raise KeyError when shutdown
            proc_usages.pop(proc_seq, None)
            for usages in name_map_usages.values():
                usages.pop(proc_seq, None)

        self._proc_consistency_handle = call_later(
            delay,
            self.proc_consistency,
            processes,
            name_map_usages,
            proc_usages,
            call_later,
            delay,
        )

    def statistic_info(
        self,
        processes: OrderedDict[int, WorkerProcess],
        name_map_usages: defaultdict[str, ServiceUsage],
        call_later: Callable[[float, Callable, Any], TimerHandle],
        delay: float,
    ):
        # load analysis in terms of all worker process - maybe send LoadHintEvent to worker
        # simple currently: for each srv_name-srv_addr, we have this proportion: proc_count / total_count
        # our target is to balance this proportion of all workers in each srv_name-srv_addr
        for srv_tag, srv_usages in name_map_usages.items():
            srv_name, srv_addr = srv_tag.split("/")
            for proc_seq, usage in srv_usages.usages.items():
                bytes_data = ProcEvent(
                    evt_tp=LOAD_HINT,
                    srv_evt=LoadHintEvent(
                        srv_name=srv_name,
                        srv_addr=srv_addr,
                        weight=pack(">1B", int(usage.proportion * 100)),
                    ),
                ).SerializeToString()
                bytes_length = len(bytes_data)
                data = pack(">1B", bytes_length) + bytes_data
                processes[proc_seq].feed_data_nowait(data)

        self._statistic_info_handle = call_later(
            delay, self.statistic_info, processes, name_map_usages, call_later, delay
        )

    # now when dont use discovery, there is nothing in statistic manager,
    # TODO later maybe add something else
    async def start(self):
        if self.use_discovery:
            if self.work_mode:
                call_later = get_running_loop().call_later
                workers, name_map_usages = self._workers, self.name_map_usages
                self._statistic_info_handle = call_later(
                    600,
                    self.statistic_info,
                    workers,
                    name_map_usages,
                    call_later,
                    600,
                )
                self._proc_consistency_handle = call_later(
                    5,
                    self.proc_consistency,
                    workers,
                    name_map_usages,
                    self._proc_usages,
                    call_later,
                    5,
                )
                self._extract_info_task = create_task(
                    self.extract_info_multi_mode(self._proc_recv_queue)
                )
            else:
                self._extract_info_task = create_task(
                    self.extract_info_single_mode(self._proc_recv_queue)
                )

    async def stop(self, exc):
        if self.use_discovery:
            if self.work_mode:
                handle: TimerHandle = self._proc_consistency_handle
                self._proc_consistency_handle = None
                handle.cancel()

                handle = self._statistic_info_handle
                self._statistic_info_handle = None
                handle.cancel()

            task, self._extract_info_task = self._extract_info_task, None
            task.cancel()
            await wait([task])
