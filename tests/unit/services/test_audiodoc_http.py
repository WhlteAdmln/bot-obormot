# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the shared audiodoc HTTP plumbing."""

import aiohttp
import pytest

from bot_obormot.common.http_limits import MAX_ERROR_BODY_BYTES
from bot_obormot.errors import AudiodocUnavailableError
from bot_obormot.services.audiodoc_http import (
    FormResponse,
    bearer_headers,
    endpoint_url,
    post_form,
    require_base_url,
)
from tests.support.audio_documents import FakeHTTPResponse, FakeHTTPSession
from tests.support.settings import make_settings


def test_endpoint_url_keeps_the_base_path_and_query() -> None:
    base = "https://audio.example/api/?token=Ω1"
    expected = "https://audio.example/api/transcribe?token=Ω1"
    assert endpoint_url(base, "transcribe") == expected, "the path must be joined"


def test_bearer_headers_are_empty_without_a_key() -> None:
    expected_empty: dict[str, str] = {}
    assert bearer_headers("") == expected_empty, "no key means no authorization header"


def test_require_base_url_rejects_missing_url() -> None:
    settings = make_settings(AUDIODOC_URL="")
    expected = "AUDIODOC_URL is not configured"
    with pytest.raises(AudiodocUnavailableError, match="not configured") as caught:
        require_base_url(settings, AudiodocUnavailableError)
    assert str(caught.value) == expected, "a missing URL was not rejected"


def test_form_response_detail_of_a_missing_body_is_empty() -> None:
    expected_empty = ""
    assert FormResponse(413, None).detail == expected_empty, (
        "a dropped body has no detail"
    )


def test_form_response_rejects_a_non_json_body() -> None:
    body = b"<html>"
    expected = "Expecting value"
    with pytest.raises(ValueError, match="Expecting value") as caught:
        FormResponse(200, body).json()
    assert expected in str(caught.value), "an HTML body was parsed as JSON"


def test_form_response_detail_marks_a_truncated_body() -> None:
    response = FormResponse(502, b"upstream \xd0\xbe\xd1\x88", truncated=True)
    expected = "upstream ош [truncated]"
    assert response.detail == expected, "a truncated body must be marked"


def test_form_response_detail_cuts_long_text_to_the_detail_limit() -> None:
    body = "Щ".encode() * 1001
    expected = "Щ" * 1000 + " [truncated]"
    assert FormResponse(500, body).detail == expected, "long text is not cut"


@pytest.mark.asyncio
async def test_post_form_keeps_the_start_of_a_long_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b"E" * (MAX_ERROR_BODY_BYTES + 37)
    session = FakeHTTPSession(FakeHTTPResponse(status=500, body=body))
    monkeypatch.setattr(aiohttp, "ClientSession", session)
    response = await post_form(
        "http://engine.test/process",
        aiohttp.FormData(),
        aiohttp.ClientTimeout(total=3),
        {},
    )
    expected = FormResponse(500, b"E" * MAX_ERROR_BODY_BYTES, truncated=True)
    assert response == expected, "a long error body must keep its first bytes"
