# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the fake audiodoc support server."""

import json
from pathlib import Path

import aiohttp
import pytest

from bot_obormot.errors import (
    AudiodocAPIError,
    AudiodocTimeoutError,
    AudiodocUnavailableError,
)
from bot_obormot.services.audio.client import transcribe_audio
from bot_obormot.services.documents.client import process_document
from bot_obormot.settings import Settings
from tests.support.fake_audiodoc import FakeAudiodoc, FakeResponseOptions
from tests.support.settings import make_settings

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "contract"
    / "fixtures"
    / "audiodoc_responses.json"
)


def _bot_settings(server: FakeAudiodoc, **overrides: object) -> Settings:
    """Build settings that point both real bot clients at the fake server."""
    return make_settings(
        AUDIODOC_URL=server.base_url.rstrip("/"),
        AUDIODOC_AUDIO_KEY=server.whisper_api_key,
        AUDIODOC_DOCUMENT_KEY=server.document_api_key,
        **overrides,
    )


@pytest.mark.parametrize("endpoint", ["health", "ready"])
@pytest.mark.asyncio
async def test_fake_audiodoc_answers_probe_with_ok_status(endpoint: str) -> None:
    async with (
        FakeAudiodoc() as server,
        aiohttp.ClientSession() as session,
        session.get(f"{server.base_url}{endpoint}") as response,
    ):
        expected_http_status = 200
        assert response.status == expected_http_status, "the probe did not answer 200"


@pytest.mark.parametrize(
    ("endpoint", "expected_body"),
    [("health", {"status": "ok"}), ("ready", {"status": "ready"})],
)
@pytest.mark.asyncio
async def test_fake_audiodoc_answers_probe_with_status_body(
    endpoint: str, expected_body: dict[str, str]
) -> None:
    async with (
        FakeAudiodoc() as server,
        aiohttp.ClientSession() as session,
        session.get(f"{server.base_url}{endpoint}") as response,
    ):
        body = await response.json()

    assert body == expected_body, "the probe answered another body"


@pytest.mark.asyncio
async def test_fake_audiodoc_serves_contract_transcription() -> None:
    contract = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))

    async with FakeAudiodoc() as server:
        text = await transcribe_audio(
            b"audio", "voice.ogg", settings=_bot_settings(server)
        )

    assert text == contract["transcribe"]["text"], "the transcription differs"


@pytest.mark.asyncio
async def test_fake_audiodoc_serves_contract_document_response() -> None:
    contract = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))

    async with FakeAudiodoc() as server:
        result = await process_document(
            b"document", "note.txt", settings=_bot_settings(server)
        )

    assert result == contract["process_document"], "the document response differs"


async def _post_transcribe(server: FakeAudiodoc) -> aiohttp.ClientResponse:
    form = aiohttp.FormData()
    form.add_field("file", b"audio", filename="audio.ogg")
    headers = {"Authorization": f"Bearer {server.whisper_api_key}"}
    async with (
        aiohttp.ClientSession(headers=headers) as session,
        session.post(f"{server.base_url}transcribe", data=form) as response,
    ):
        await response.read()
        return response


@pytest.mark.asyncio
async def test_fake_audiodoc_returns_the_configured_status() -> None:
    status = 503
    async with FakeAudiodoc() as server:
        server.set_behavior(
            "transcribe",
            FakeResponseOptions(status=status, retry_after_seconds=17),
        )
        response = await _post_transcribe(server)

    assert response.status == status, "the fake returned another status"


@pytest.mark.asyncio
async def test_fake_audiodoc_returns_the_configured_retry_after() -> None:
    async with FakeAudiodoc() as server:
        server.set_behavior(
            "transcribe",
            FakeResponseOptions(status=503, retry_after_seconds=23),
        )
        response = await _post_transcribe(server)

    expected_retry_after = "23"
    retry_after = response.headers["Retry-After"]
    assert retry_after == expected_retry_after, "the Retry-After header differs"


@pytest.mark.parametrize("status", [401, 413, 415, 422, 503])
@pytest.mark.asyncio
async def test_fake_audiodoc_can_return_configured_http_errors(
    status: int,
) -> None:
    async with FakeAudiodoc() as server:
        settings = _bot_settings(server)
        server.set_behavior(
            "transcribe",
            FakeResponseOptions(status=status, retry_after_seconds=17),
        )

        with pytest.raises(
            AudiodocAPIError, match=f"audiodoc HTTP {status}"
        ) as excinfo:
            await transcribe_audio(b"audio", settings=settings)

    assert excinfo.type is AudiodocAPIError, "the HTTP error was not reported"


@pytest.mark.asyncio
async def test_fake_audiodoc_can_return_invalid_json() -> None:
    async with FakeAudiodoc() as server:
        settings = _bot_settings(server)
        server.set_behavior(
            "transcribe",
            FakeResponseOptions(invalid_json=True),
        )

        with pytest.raises(AudiodocAPIError, match="invalid JSON") as excinfo:
            await transcribe_audio(b"audio", settings=settings)

    assert excinfo.type is AudiodocAPIError, "invalid JSON was not reported"


@pytest.mark.asyncio
async def test_fake_audiodoc_can_delay_a_response() -> None:
    async with FakeAudiodoc() as server:
        settings = _bot_settings(server, AUDIODOC_AUDIO_TIMEOUT=0.01)
        server.set_behavior(
            "transcribe",
            FakeResponseOptions(delay=0.05),
        )

        with pytest.raises(AudiodocTimeoutError, match="timed out") as excinfo:
            await transcribe_audio(b"audio", settings=settings)

    assert excinfo.type is AudiodocTimeoutError, "the delay did not time out"


@pytest.mark.asyncio
async def test_fake_audiodoc_can_truncate_a_response() -> None:
    async with FakeAudiodoc() as server:
        settings = _bot_settings(server)
        server.set_behavior(
            "transcribe",
            FakeResponseOptions(truncated_body=True),
        )

        with pytest.raises(
            AudiodocUnavailableError, match="connection error"
        ) as excinfo:
            await transcribe_audio(b"audio", settings=settings)

    assert excinfo.type is AudiodocUnavailableError, "truncation was not reported"
