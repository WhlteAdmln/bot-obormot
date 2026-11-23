# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for per-user message throttling."""

from types import SimpleNamespace

import pytest

from bot_obormot.middlewares import throttle as throttle_module


@pytest.mark.asyncio
async def test_throttle_allows_limit_and_drops_next_event() -> None:
    """Throttle allows limit and drops next event."""
    ticks = iter((1.0, 2.0, 3.0, 4.0))
    middleware = throttle_module.ThrottleMiddleware(
        max_events=3,
        window_seconds=10,
        clock=lambda: next(ticks),
    )
    calls = []

    async def handler(event: object, _data: object) -> str:
        calls.append(event)
        return "handled"

    user_data = {"event_from_user": SimpleNamespace(id=42)}
    results = [await middleware(handler, index, user_data) for index in range(4)]

    assert results == ["handled", "handled", "handled", None]
    assert calls == [0, 1, 2]


@pytest.mark.asyncio
async def test_throttle_expires_events_after_window() -> None:
    """Throttle expires events after window."""
    ticks = iter((1.0, 12.0))
    middleware = throttle_module.ThrottleMiddleware(
        max_events=1,
        window_seconds=10,
        clock=lambda: next(ticks),
    )
    calls = []

    async def handler(event: object, _data: object) -> str:
        calls.append(event)
        return "handled"

    user_data = {"event_from_user": SimpleNamespace(id=42)}

    expected_text = "handled"
    assert await middleware(handler, "first", user_data) == expected_text
    expected_text = "handled"
    assert await middleware(handler, "second", user_data) == expected_text
    assert calls == ["first", "second"]


@pytest.mark.asyncio
async def test_throttle_drops_events_without_sender() -> None:
    """Throttle drops events without sender."""
    middleware = throttle_module.ThrottleMiddleware()
    calls = []

    async def handler(event: object, _data: object) -> None:
        calls.append(event)

    assert await middleware(handler, "event", {"event_from_user": None}) is None
    expected_empty = []
    assert calls == expected_empty, "expected an empty list"


async def _send(middleware: object, user_id: int) -> object:
    async def handler(event: object, _data: object) -> object:
        return event

    return await middleware(
        handler,
        user_id,
        {"event_from_user": SimpleNamespace(id=user_id)},
    )


async def _fill_two_slot_registry() -> object:
    middleware = throttle_module.ThrottleMiddleware(
        max_events=1,
        max_tracked_users=2,
    )
    for user_id in (11, 22, 33):
        await _send(middleware, user_id)
    return middleware


@pytest.mark.asyncio
async def test_throttle_forgets_the_oldest_user_when_the_registry_is_full() -> None:
    middleware = await _fill_two_slot_registry()
    evicted = 11
    assert await _send(middleware, evicted) == evicted, "an evicted user is fresh"


@pytest.mark.asyncio
async def test_throttle_keeps_tracking_the_newest_user() -> None:
    middleware = await _fill_two_slot_registry()
    assert await _send(middleware, 33) is None, "the newest user stays throttled"


def test_throttle_rejects_invalid_limits() -> None:
    """Throttle rejects invalid limits."""
    with pytest.raises(ValueError, match="max_events"):
        throttle_module.ThrottleMiddleware(max_events=0)

    with pytest.raises(ValueError, match="window_seconds"):
        throttle_module.ThrottleMiddleware(window_seconds=0)

    with pytest.raises(ValueError, match="max_tracked_users"):
        throttle_module.ThrottleMiddleware(max_tracked_users=0)


@pytest.mark.asyncio
async def test_throttle_isolates_users() -> None:
    """One user's burst does not consume another user's event allowance."""
    ticks = iter((1.0, 2.0, 3.0, 4.0, 5.0))
    middleware = throttle_module.ThrottleMiddleware(
        max_events=2,
        window_seconds=10,
        clock=lambda: next(ticks),
    )
    calls = []

    async def handler(event: object, _data: object) -> str:
        calls.append(event)
        return "handled"

    sequence = (
        (1, "user-1-first"),
        (2, "user-2-first"),
        (1, "user-1-second"),
        (1, "user-1-over-limit"),
        (2, "user-2-second"),
    )
    results = []

    for user_id, event in sequence:
        result = await middleware(
            handler,
            event,
            {"event_from_user": SimpleNamespace(id=user_id)},
        )
        results.append(result)

    assert results == ["handled", "handled", "handled", None, "handled"]
    assert calls == [
        "user-1-first",
        "user-2-first",
        "user-1-second",
        "user-2-second",
    ]
