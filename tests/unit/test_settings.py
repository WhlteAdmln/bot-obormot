# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for settings."""

import importlib
import importlib.util

import pytest

from bot_obormot.settings import get_settings


@pytest.mark.parametrize(
    ("module_name", "attribute"),
    [
        ("bot_obormot.config", "config"),
        ("bot_obormot.config", "Config"),
        ("bot_obormot.settings", "config"),
        ("bot_obormot.settings", "Config"),
        ("bot_obormot.config.model", "config"),
    ],
)
def test_legacy_config_proxy_and_config_alias_are_removed(
    module_name: str, attribute: str
) -> None:
    module = importlib.import_module(module_name)
    assert not hasattr(module, attribute), f"{module_name} still has {attribute}"


def test_stream_update_interval_is_not_an_environment_setting() -> None:
    settings_class = importlib.import_module("bot_obormot.settings").Settings
    name = "STREAM_UPDATE_INTERVAL"
    assert not hasattr(settings_class, name), "the stream interval is a setting"


def test_settings_have_no_config_submodule() -> None:
    module_name = "bot_obormot.config.settings"
    spec = importlib.util.find_spec(module_name)
    assert spec is None, "the legacy settings module still exists"


def test_settings_have_a_single_public_import_path() -> None:
    settings_module = importlib.import_module("bot_obormot.settings")
    config_module = importlib.import_module("bot_obormot.config")
    duplicated = [
        name for name in settings_module.__all__ if hasattr(config_module, name)
    ]
    expected_empty: list[str] = []
    assert duplicated == expected_empty, "settings are exported from config too"


def test_bot_settings_reexports_get_settings() -> None:
    cache_module = importlib.import_module("bot_obormot.config.model.cache")
    assert get_settings is cache_module.get_settings, "get_settings is not reexported"
