# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Mutable state of one message aggregation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class _AggregationState:
    parts: list[str]
    last_activity: float
    event: asyncio.Event = field(default_factory=asyncio.Event)
    future: asyncio.Future[str] | None = None
