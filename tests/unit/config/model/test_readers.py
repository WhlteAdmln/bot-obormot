# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the environment reader."""

from bot_obormot.config.model.readers import EnvironmentReader


def test_reads_a_stripped_lowercase_string() -> None:
    environ = {"LLM_TOKEN_COUNTING": "  LlamaCpp \t"}
    reader = EnvironmentReader(environ)

    value = reader.read_str("LLM_TOKEN_COUNTING", "auto", strip=True, lower=True)

    expected = "llamacpp"
    assert value == expected, "the string is not stripped and lowercased"


def test_returns_the_default_for_an_invalid_integer() -> None:
    environ = {"LLM_MAX_TOKENS": "много"}
    reader = EnvironmentReader(environ)
    default = 517

    value = reader.read_int("LLM_MAX_TOKENS", default)

    assert value == default, "an invalid integer does not fall back to the default"


def test_records_an_error_for_an_invalid_integer() -> None:
    environ = {"LLM_TIMEOUT": "-3"}
    reader = EnvironmentReader(environ)

    reader.read_int("LLM_TIMEOUT", 300)

    expected_count = 1
    assert len(reader.errors) == expected_count, "the invalid integer is not recorded"


def test_returns_none_for_an_invalid_optional_integer() -> None:
    environ = {"LLM_CONTEXT_SIZE": "4k"}
    reader = EnvironmentReader(environ)

    value = reader.read_optional_int("LLM_CONTEXT_SIZE")

    assert value is None, "an invalid optional integer is not replaced by None"


def test_returns_the_default_for_an_out_of_range_float() -> None:
    environ = {"LLM_TOP_P": "1.25"}
    reader = EnvironmentReader(environ)
    default = 0.85

    value = reader.read_float("LLM_TOP_P", default, minimum=0.0, maximum=1.0)

    assert value == default, "an out-of-range float does not fall back to the default"


def test_returns_the_default_for_an_invalid_boolean() -> None:
    environ = {"ALLOW_ALL_USERS": "наверное"}
    reader = EnvironmentReader(environ)

    value = reader.read_bool("ALLOW_ALL_USERS", default=True)

    assert value is True, "an invalid boolean does not fall back to the default"


def test_returns_no_ids_for_an_invalid_list() -> None:
    environ = {"ADMIN_IDS": "41, сорок два"}
    reader = EnvironmentReader(environ)

    value = reader.read_ids("ADMIN_IDS")

    expected_empty: set[int] = set()
    assert value == expected_empty, "an invalid ID list is not replaced by an empty set"
