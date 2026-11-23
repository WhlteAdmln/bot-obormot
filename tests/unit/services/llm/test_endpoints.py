# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm endpoints."""

from dataclasses import replace

from bot_obormot.services.llm import endpoints
from bot_obormot.settings import Settings


def test_server_url_removes_trailing_slashes_and_v1() -> None:
    """Server url removes trailing slashes and v1."""
    settings = replace(
        Settings(),
        LLM_BASE_URL="http://localhost:8080/v1///",
    )
    expected_server_url = "http://localhost:8080"
    assert endpoints.server_url(settings) == expected_server_url
