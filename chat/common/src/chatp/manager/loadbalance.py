from typing import Optional, Generator
from asyncio import StreamWriter, sleep

from ..rpc.grpc_service import GrpcStubRepositorty, GrpcStubGroup, GrpcStub
from ..utils.types import ServiceName
from ..utils.model import AsyncIOQueueWriterWrapper, ThreadsafeQueueWriterWrapper
from ..proto.processes.event_pb2 import (
    Event as ProcEvent,
    LoadHintEvent,
)


class LoadBalancer:
    __slots__ = "services"

    def __init__(self, services: dict[ServiceName, GrpcStubRepositorty]):
        self.services = services  #

    async def load_event_cb(self, event: ProcEvent):
        event: LoadHintEvent = event.load_evt

    async def write_load_back(
        self,
        writer: StreamWriter | AsyncIOQueueWriterWrapper | ThreadsafeQueueWriterWrapper,
    ):
        while True:
            await sleep(600)  # 10min

    # TODO Add HealthCheck
    def route(
        self,
        srv_name: str,
        *,
        domain: Optional[str] = None,
        hash_key: Optional[str] = None,
    ) -> Optional[GrpcStub]:
        srv_repo = self.services[srv_name]
        if hash_key is None:  # random
            rb = srv_repo.round_robin
            if rb.items:
                generator: Generator[GrpcStubGroup, None] = rb.flick()
                for stub_group in generator:
                    stub = stub_group.get(domain)
                    if stub is not None:
                        srv_repo.notify_connection_alive(stub_group)
                        return stub

                    srv_repo.notify_connection_lost(stub_group)
        else:  # hashring
            # addr: str = srv_repo.ring.get_node_hostname(key)
            addr: str = srv_repo.ring.get_node(hash_key)
            if addr and (stub_group := srv_repo.services.get(addr)) is not None:
                return stub_group.get(domain)
