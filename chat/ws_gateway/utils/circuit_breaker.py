import aiomisc


class CircuitBreakerMixin:
    exceptions = []

    def cb_initialize(self, error_ratio: float, response_time: int, broken_time: int):
        self._cb = aiomisc.CircuitBreaker(
            error_ratio=error_ratio,
            response_time=response_time,
            exceptions=self.__class__.exceptions,
            broken_time=broken_time,
        )
