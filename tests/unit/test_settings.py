# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for settings."""

import importlib
import importlib.util

from bot_obormot.settings import get_settings


def test_legacy_config_proxy_and_config_alias_are_removed() -> None:
    """The legacy proxy and Config alias are no longer exported."""
    config_module = importlib.import_module("bot_obormot.config")
    settings_module = importlib.import_module("bot_obormot.settings")
    model_module = importlib.import_module("bot_obormot.config.model")

    assert not hasattr(config_module, "config")
    assert not hasattr(config_module, "Config")
    assert not hasattr(settings_module, "config")
    assert not hasattr(settings_module, "Config")
    assert not hasattr(model_module, "config")


def test_stream_update_interval_is_not_an_environment_setting() -> None:
    """Stream update interval is not an application setting."""
    settings_class = importlib.import_module("bot_obormot.settings").Settings

    assert not hasattr(settings_class, "STREAM_UPDATE_INTERVAL")


def test_settings_have_a_single_public_import_path() -> None:
    """Settings are exported from the settings module only, not from config."""
    settings_module = importlib.import_module("bot_obormot.settings")
    config_module = importlib.import_module("bot_obormot.config")
    model_module = importlib.import_module("bot_obormot.config.model")

    assert importlib.util.find_spec("bot_obormot.config.settings") is None
    for name in settings_module.__all__:
        assert getattr(settings_module, name) is getattr(model_module, name)
        assert not hasattr(config_module, name)


def test_bot_settings_reexports_get_settings() -> None:
    """Bot settings reexports the shared settings getter."""
    model_module = importlib.import_module("bot_obormot.config.model")
    assert get_settings is model_module.get_settings
