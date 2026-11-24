# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Mutable state of one message aggregation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram.types import Message


@dataclass
class _AggregationState:
    parts: list[str]
    last_activity: float
    event: asyncio.Event = field(default_factory=asyncio.Event)
    future: asyncio.Future[str] | None = None
    # The last message that was added to the aggregation.
    last_message: Message | None = None
