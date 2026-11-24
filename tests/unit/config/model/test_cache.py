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
def test_get_settings_is_cached_until_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPERVISOR_ID", "123")
    first = get_settings()
    monkeypatch.setenv("SUPERVISOR_ID", "456")

    assert get_settings() is first
    expected_supervisor_id = 123
    assert expected_supervisor_id == get_settings().SUPERVISOR_ID

    reset_settings_cache()
    expected_supervisor_id = 456
    assert expected_supervisor_id == get_settings().SUPERVISOR_ID
