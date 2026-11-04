"""Tests for per-user message throttling."""

from types import SimpleNamespace

import pytest

from bot.middlewares import throttle as throttle_module


@pytest.mark.asyncio
async def test_throttle_allows_limit_and_drops_next_event():
    ticks = iter((1.0, 2.0, 3.0, 4.0))
    middleware = throttle_module.ThrottleMiddleware(
        max_events=3,
        window_seconds=10,
        clock=lambda: next(ticks),
    )
    calls = []

    async def handler(event, data):
        calls.append(event)
        return "handled"

    user_data = {"event_from_user": SimpleNamespace(id=42)}
    results = [await middleware(handler, index, user_data) for index in range(4)]

    assert results == ["handled", "handled", "handled", None]
    assert calls == [0, 1, 2]


@pytest.mark.asyncio
async def test_throttle_expires_events_after_window():
    ticks = iter((1.0, 12.0))
    middleware = throttle_module.ThrottleMiddleware(
        max_events=1,
        window_seconds=10,
        clock=lambda: next(ticks),
    )
    calls = []

    async def handler(event, data):
        calls.append(event)
        return "handled"

    user_data = {"event_from_user": SimpleNamespace(id=42)}

    assert await middleware(handler, "first", user_data) == "handled"
    assert await middleware(handler, "second", user_data) == "handled"
    assert calls == ["first", "second"]


@pytest.mark.asyncio
async def test_throttle_drops_events_without_sender():
    middleware = throttle_module.ThrottleMiddleware()
    calls = []

    async def handler(event, data):
        calls.append(event)

    assert await middleware(handler, "event", {"event_from_user": None}) is None
    assert calls == []


@pytest.mark.asyncio
async def test_throttle_keeps_tracking_registry_bounded():
    middleware = throttle_module.ThrottleMiddleware(
        max_events=1,
        max_tracked_users=2,
    )

    async def handler(event, data):
        return event

    for user_id in (1, 2, 3):
        result = await middleware(
            handler,
            user_id,
            {"event_from_user": SimpleNamespace(id=user_id)},
        )
        assert result == user_id

    assert len(middleware._events) == 2
    assert list(middleware._events) == [2, 3]


def test_throttle_rejects_invalid_limits():
    with pytest.raises(ValueError, match="max_events"):
        throttle_module.ThrottleMiddleware(max_events=0)

    with pytest.raises(ValueError, match="window_seconds"):
        throttle_module.ThrottleMiddleware(window_seconds=0)

    with pytest.raises(ValueError, match="max_tracked_users"):
        throttle_module.ThrottleMiddleware(max_tracked_users=0)
