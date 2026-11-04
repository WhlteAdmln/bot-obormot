from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class _AggregationState:
    parts: list[str]
    last_activity: float
    event: asyncio.Event = field(default_factory=asyncio.Event)
    future: asyncio.Future[str] | None = None
