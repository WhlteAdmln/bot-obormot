# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for per-user message throttling."""

from collections.abc import Iterable
from types import SimpleNamespace

import pytest

from bot_obormot.middlewares.throttle import ThrottleMiddleware
from tests.support.middleware_handler import RecordingHandler


def _sender(user_id: int) -> dict[str, object]:
    return {"event_from_user": SimpleNamespace(id=user_id)}


def _clock(ticks: Iterable[float]) -> object:
    remaining = iter(ticks)
    return lambda: next(remaining)


async def _send_all(
    middleware: ThrottleMiddleware,
    handler: RecordingHandler,
    events: Iterable[tuple[int, str]],
) -> list[object]:
    return [
        await middleware(handler, event, _sender(user_id)) for user_id, event in events
    ]


def _construction_error(**limits: float) -> str:
    try:
        ThrottleMiddleware(**limits)
    except ValueError as error:
        return str(error)
    return ""


async def _send(middleware: ThrottleMiddleware, user_id: int) -> object:
    return await middleware(RecordingHandler(user_id), user_id, _sender(user_id))


async def _fill_two_slot_registry() -> ThrottleMiddleware:
    middleware = ThrottleMiddleware(max_events=1, max_tracked_users=2)
    for user_id in (11, 22, 33):
        await _send(middleware, user_id)
    return middleware


@pytest.mark.asyncio
async def test_drops_the_event_after_the_limit() -> None:
    middleware = ThrottleMiddleware(
        max_events=3, window_seconds=10, clock=_clock((1.0, 2.0, 3.0, 4.0))
    )
    events = [(42, "ping"), (42, "ping again"), (42, "spam"), (42, "flood")]
    results = await _send_all(middleware, RecordingHandler(), events)
    expected = ["handled", "handled", "handled", None]
    assert results == expected, "the event over the limit was not dropped"


@pytest.mark.asyncio
async def test_passes_only_events_within_the_limit_to_the_handler() -> None:
    middleware = ThrottleMiddleware(
        max_events=2, window_seconds=10, clock=_clock((1.0, 1.0, 1.0))
    )
    handler = RecordingHandler()
    await _send_all(middleware, handler, [(42, "a"), (42, "b"), (42, "c")])
    expected = ["a", "b"]
    assert handler.events == expected, "a dropped event reached the handler"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("second_tick", "expected"),
    [(11.0, "handled"), (10.999, None), (1.0, None)],
    ids=["window-over", "just-inside", "same-instant"],
)
async def test_expires_events_exactly_at_the_window_end(
    second_tick: float, expected: object
) -> None:
    middleware = ThrottleMiddleware(
        max_events=1, window_seconds=10, clock=_clock((1.0, second_tick))
    )
    results = await _send_all(middleware, RecordingHandler(), [(7, "a"), (7, "b")])
    assert results[-1] == expected, "the window boundary is wrong"


@pytest.mark.asyncio
async def test_dropped_events_do_not_extend_the_window() -> None:
    middleware = ThrottleMiddleware(
        max_events=1, window_seconds=10, clock=_clock((1.0, 5.0, 9.0, 11.5))
    )
    events = [(7, "first"), (7, "flood"), (7, "flood"), (7, "later")]
    results = await _send_all(middleware, RecordingHandler(), events)
    expected = ["handled", None, None, "handled"]
    assert results == expected, "a flood of dropped events kept the user blocked"


@pytest.mark.asyncio
async def test_drops_events_without_sender() -> None:
    handler = RecordingHandler()
    result = await ThrottleMiddleware()(handler, "event", {"event_from_user": None})
    expected = (None, [])
    assert (result, handler.events) == expected, "an anonymous event was handled"


@pytest.mark.asyncio
async def test_forgets_the_oldest_user_when_the_registry_is_full() -> None:
    middleware = await _fill_two_slot_registry()
    evicted = 11
    assert await _send(middleware, evicted) == evicted, "an evicted user is fresh"


@pytest.mark.asyncio
async def test_keeps_tracking_the_newest_user() -> None:
    middleware = await _fill_two_slot_registry()
    newest = 33
    assert await _send(middleware, newest) is None, "the newest user stays throttled"


@pytest.mark.parametrize(
    ("limits", "expected"),
    [
        ({"max_events": 0}, "max_events must be positive"),
        ({"max_events": -5}, "max_events must be positive"),
        ({"window_seconds": 0}, "window_seconds must be positive"),
        ({"window_seconds": -0.25}, "window_seconds must be positive"),
        ({"max_tracked_users": 0}, "max_tracked_users must be positive"),
        ({"max_tracked_users": -3}, "max_tracked_users must be positive"),
    ],
)
def test_rejects_limits_that_are_not_positive(
    limits: dict[str, float], expected: str
) -> None:
    error = _construction_error(**limits)
    assert error == expected, "an invalid limit was accepted"


@pytest.mark.asyncio
async def test_counts_each_user_separately() -> None:
    middleware = ThrottleMiddleware(
        max_events=2, window_seconds=10, clock=_clock((1.0, 2.0, 3.0, 4.0, 5.0))
    )
    events = [
        (1, "user-1-first"),
        (2, "user-2-first"),
        (1, "user-1-second"),
        (1, "user-1-over-limit"),
        (2, "user-2-second"),
    ]
    results = await _send_all(middleware, RecordingHandler(), events)
    expected = ["handled", "handled", "handled", None, "handled"]
    assert results == expected, "one user's events counted against another"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first_id", "second_id"),
    [(0, -1), (2**63 - 1, -(2**63)), (-1002003004005, 1002003004005)],
    ids=["zero-and-minus-one", "extremes", "negated"],
)
async def test_keeps_unusual_ids_apart(first_id: int, second_id: int) -> None:
    middleware = ThrottleMiddleware(max_events=1, window_seconds=10)
    events = [(first_id, "a"), (second_id, "b")]
    results = await _send_all(middleware, RecordingHandler(), events)
    expected = ["handled", "handled"]
    assert results == expected, "two different IDs share one counter"
