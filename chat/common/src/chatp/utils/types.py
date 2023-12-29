from typing import TypeVar
from functools import partial
from weakref import ReferenceType


def f_(x: int):
    pass


PartialMethodType = type(partial(f_, x=1))
ProcessManager = TypeVar("ProcessManager")
ProcessManagerWeakref = ReferenceType(ProcessManager)
GrpcManager = TypeVar("GrpcManager")
StubClassType = TypeVar("StubClassType")

ServiceName = str
ServiceAddr = str
PlatformId = str
UID = int
