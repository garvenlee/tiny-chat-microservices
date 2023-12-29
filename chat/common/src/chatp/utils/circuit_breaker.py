from aiomisc import CircuitBreaker
from typing import Optional, Callable


class CircuitBreakerMixin:
    exceptions = []

    ERROR_RATIO: float = 0.2
    RESPONSE_TIME: int = 10
    PASSING_TIME: int = 1
    BROKEN_TIME: int = 1
    RECOVERY_TIME: int = 1

    __slots__ = ("_circuit_breaker",)

    def cb_initialize(
        self,
        error_ratio: Optional[float] = None,
        response_time: Optional[int] = None,
        passing_time: Optional[int] = None,
        broken_time: Optional[int] = None,
        recovery_time: Optional[int] = None,
        exception_inspector: Optional[Callable[[Exception], bool]] = None,
    ):
        self._circuit_breaker = CircuitBreaker(
            error_ratio=error_ratio or self.ERROR_RATIO,
            response_time=response_time or self.RESPONSE_TIME,
            passing_time=passing_time or self.PASSING_TIME,
            broken_time=broken_time or self.BROKEN_TIME,
            recovery_time=recovery_time or self.RECOVERY_TIME,
            exceptions=self.exceptions,
            exception_inspector=exception_inspector,
        )
