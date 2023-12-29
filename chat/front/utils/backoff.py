from random import uniform


# Maximum backoff between each retry in seconds
DEFAULT_CAP = 0.512
# Minimum backoff between each retry in seconds
DEFAULT_BASE = 0.008


class EqualJitterBackoff:
    """Equal jitter backoff upon failure"""

    def __init__(self, cap=DEFAULT_CAP, base=DEFAULT_BASE):
        """
        `cap`: maximum backoff time in seconds
        `base`: base backoff time in seconds
        """
        self._cap = cap
        self._base = base

        self._last_delay = 0

    @property
    def is_dirty(self):
        return self._last_delay > 0

    def reset(self):
        self._last_delay = 0

    def compute(self, failures):
        temp = min(self._cap, self._base * 2**failures) / 2
        delay = temp + uniform(0, temp)
        self._last_delay = delay
        return delay
