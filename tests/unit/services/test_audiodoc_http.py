# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the shared audiodoc HTTP plumbing."""

import pytest

from bot_obormot.errors import AudiodocUnavailableError
from bot_obormot.services.audiodoc_http import (
    FormResponse,
    bearer_headers,
    endpoint_url,
    require_base_url,
)
from tests.support.settings import make_settings


def test_endpoint_url_keeps_the_base_path_and_query() -> None:
    base = "https://audio.example/api/?token=Ω1"
    expected = "https://audio.example/api/transcribe?token=Ω1"
    assert endpoint_url(base, "transcribe") == expected, "the path must be joined"


def test_bearer_headers_are_empty_without_a_key() -> None:
    assert not bearer_headers(""), "no key means no authorization header"


def test_require_base_url_rejects_missing_url() -> None:
    settings = make_settings(AUDIODOC_URL="")
    with pytest.raises(AudiodocUnavailableError, match="not configured"):
        require_base_url(settings, AudiodocUnavailableError)


def test_form_response_detail_of_a_missing_body_is_empty() -> None:
    assert not FormResponse(413, None).detail, "a dropped body has no detail"


def test_form_response_rejects_a_non_json_body() -> None:
    with pytest.raises(ValueError, match="Expecting value"):
        FormResponse(200, b"<html>").json()
