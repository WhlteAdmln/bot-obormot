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


@pytest.mark.asyncio
async def test_fake_audiodoc_serves_contract_responses_to_real_clients() -> None:
    """Serve fixture responses over HTTP to both real bot clients."""
    contract = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))

    async with FakeAudiodoc() as server:
        settings = _bot_settings(server)

        async with aiohttp.ClientSession() as session:
            for endpoint, expected_status in (
                ("health", "ok"),
                ("ready", "ready"),
            ):
                async with session.get(f"{server.base_url}{endpoint}") as response:
                    expected_status_2 = 200
                    assert response.status == expected_status_2
                    assert await response.json() == {"status": expected_status}

        assert (
            await transcribe_audio(b"audio", "voice.ogg", settings=settings)
            == contract["transcribe"]["text"]
        )
        assert (
            await process_document(
                b"document",
                "note.txt",
                settings=settings,
            )
            == contract["process_document"]
        )


@pytest.mark.parametrize("status", [401, 413, 415, 422, 503])
@pytest.mark.asyncio
async def test_fake_audiodoc_can_return_configured_http_errors(
    status: int,
) -> None:
    """Return configured HTTP errors and Retry-After for service unavailability."""
    async with FakeAudiodoc() as server:
        settings = _bot_settings(server)
        server.set_behavior(
            "transcribe",
            FakeResponseOptions(status=status, retry_after_seconds=17),
        )

        expected_status = 503
        if status == expected_status:
            form = aiohttp.FormData()
            form.add_field("file", b"audio", filename="audio.ogg")
            async with (
                aiohttp.ClientSession(
                    headers={
                        "Authorization": f"Bearer {server.whisper_api_key}",
                    }
                ) as session,
                session.post(
                    f"{server.base_url}transcribe",
                    data=form,
                ) as response,
            ):
                assert response.status == status
                expected_retry_after = "17"
                assert response.headers["Retry-After"] == expected_retry_after
                await response.read()

        with pytest.raises(AudiodocAPIError, match=f"audiodoc HTTP {status}"):
            await transcribe_audio(b"audio", settings=settings)


@pytest.mark.asyncio
async def test_fake_audiodoc_can_return_invalid_json() -> None:
    """Return invalid JSON when the corresponding switch is enabled."""
    async with FakeAudiodoc() as server:
        settings = _bot_settings(server)
        server.set_behavior(
            "transcribe",
            FakeResponseOptions(invalid_json=True),
        )

        with pytest.raises(AudiodocAPIError, match="invalid JSON"):
            await transcribe_audio(b"audio", settings=settings)


@pytest.mark.asyncio
async def test_fake_audiodoc_can_delay_a_response() -> None:
    """Delay a response long enough to exercise the real client timeout."""
    async with FakeAudiodoc() as server:
        settings = _bot_settings(server, AUDIODOC_AUDIO_TIMEOUT=0.01)
        server.set_behavior(
            "transcribe",
            FakeResponseOptions(delay=0.05),
        )

        with pytest.raises(AudiodocTimeoutError, match="timed out"):
            await transcribe_audio(b"audio", settings=settings)


@pytest.mark.asyncio
async def test_fake_audiodoc_can_truncate_a_response() -> None:
    """Close a response before its declared content length is received."""
    async with FakeAudiodoc() as server:
        settings = _bot_settings(server)
        server.set_behavior(
            "transcribe",
            FakeResponseOptions(truncated_body=True),
        )

        with pytest.raises(AudiodocUnavailableError, match="connection error"):
            await transcribe_audio(b"audio", settings=settings)
