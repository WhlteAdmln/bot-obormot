# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Context-local correlation IDs for application log records."""

import logging
from contextvars import ContextVar

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


class CorrelationIdFilter(logging.Filter):
    """Adds the current correlation ID to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach the current context's correlation ID to a log record."""
        record.correlation_id = correlation_id.get()
        return True
