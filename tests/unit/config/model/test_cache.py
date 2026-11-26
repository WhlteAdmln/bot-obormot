# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the settings cache."""

from collections.abc import Iterator

import pytest

from bot_obormot.config.model.cache import get_settings, reset_settings_cache


@pytest.fixture(name="fresh_settings_cache")
def fixture_fresh_settings_cache() -> Iterator[None]:
    """Start with an empty settings cache and leave none behind."""
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.mark.usefixtures("fresh_settings_cache")
def test_get_settings_returns_the_cached_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPERVISOR_ID", "123")
    first = get_settings()
    monkeypatch.setenv("SUPERVISOR_ID", "456")
    assert get_settings() is first, "the settings were loaded again"


@pytest.mark.usefixtures("fresh_settings_cache")
def test_get_settings_keeps_values_until_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_supervisor_id = 777001
    monkeypatch.setenv("SUPERVISOR_ID", str(expected_supervisor_id))
    get_settings()
    monkeypatch.setenv("SUPERVISOR_ID", "888002")
    supervisor_id = get_settings().SUPERVISOR_ID
    assert supervisor_id == expected_supervisor_id, "the cache picked up a new value"


@pytest.mark.usefixtures("fresh_settings_cache")
def test_reset_settings_cache_loads_new_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_supervisor_id = 456
    monkeypatch.setenv("SUPERVISOR_ID", "123")
    get_settings()
    monkeypatch.setenv("SUPERVISOR_ID", str(expected_supervisor_id))
    reset_settings_cache()
    supervisor_id = get_settings().SUPERVISOR_ID
    assert supervisor_id == expected_supervisor_id, "the reset kept the old value"
