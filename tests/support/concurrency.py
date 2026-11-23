# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Measure how many worker threads run at the same time."""

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class ConcurrencyProbe:
    """Count concurrently running workers and remember the peak."""

    def __init__(self) -> None:
        """Start with no running workers."""
        self._condition = threading.Condition()
        self.active = 0
        self.maximum = 0

    @contextmanager
    def running(self) -> Iterator[None]:
        """Count the calling worker as running for the duration of the block."""
        with self._condition:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            self._condition.notify_all()
        try:
            yield
        finally:
            with self._condition:
                self.active -= 1

    def wait_for_active(self, count: int, timeout: float) -> bool:
        """Wait until ``count`` workers run at once; return whether they did."""
        with self._condition:
            return self._condition.wait_for(lambda: self.active >= count, timeout)
