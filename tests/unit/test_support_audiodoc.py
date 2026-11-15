# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the fake audiodoc support server."""

import json
from pathlib import Path

import aiohttp
import pytest

from bot.config import config
from bot.errors import (
    WhisperAPIError,
    WhisperTimeoutError,
    WhisperUnavailableError,
)
from bot.services.audio.client import transcribe_audio
from bot.services.documents.client import process_document
from tests.support.fake_audiodoc import FakeAudiodoc, FakeResponseOptions

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "contract"
    / "fixtures"
    / "audiodoc_responses.json"
)


def _configure_bot_clients(
    monkeypatch: pytest.MonkeyPatch,
    server: FakeAudiodoc,
) -> None:
    """Point both real bot clients at the fake audiodoc server."""
    monkeypatch.setattr(
        config,
        "WHISPER_API_URL",
        f"{server.base_url}transcribe",
    )
    monkeypatch.setattr(config, "WHISPER_API_KEY", server.whisper_api_key)
    monkeypatch.setattr(
        config,
        "DOCUMENT_API_URL",
        f"{server.base_url}process-document",
    )
    monkeypatch.setattr(config, "DOCUMENT_API_KEY", server.document_api_key)


@pytest.mark.asyncio
async def test_fake_audiodoc_serves_contract_responses_to_real_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Serve fixture responses over HTTP to both real bot clients."""
    contract = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))

    async with FakeAudiodoc() as server:
        _configure_bot_clients(monkeypatch, server)

        async with aiohttp.ClientSession() as session:
            for endpoint, expected_status in (
                ("health", "ok"),
                ("ready", "ready"),
            ):
                async with session.get(f"{server.base_url}{endpoint}") as response:
                    assert response.status == 200
                    assert await response.json() == {"status": expected_status}

        assert (
            await transcribe_audio(b"audio", "voice.ogg")
            == contract["transcribe"]["text"]
        )
        assert (
            await process_document(
                b"document",
                "note.txt",
            )
            == contract["process_document"]
        )


@pytest.mark.parametrize("status", [401, 413, 415, 422, 503])
@pytest.mark.asyncio
async def test_fake_audiodoc_can_return_configured_http_errors(
    status: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return configured HTTP errors and Retry-After for service unavailability."""
    async with FakeAudiodoc() as server:
        _configure_bot_clients(monkeypatch, server)
        server.set_behavior(
            "transcribe",
            FakeResponseOptions(status=status, retry_after_seconds=17),
        )

        if status == 503:
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
                assert response.headers["Retry-After"] == "17"
                await response.read()

        with pytest.raises(WhisperAPIError, match=f"Whisper HTTP {status}"):
            await transcribe_audio(b"audio")


@pytest.mark.asyncio
async def test_fake_audiodoc_can_return_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return invalid JSON when the corresponding switch is enabled."""
    async with FakeAudiodoc() as server:
        _configure_bot_clients(monkeypatch, server)
        server.set_behavior(
            "transcribe",
            FakeResponseOptions(invalid_json=True),
        )

        with pytest.raises(WhisperAPIError, match="invalid JSON"):
            await transcribe_audio(b"audio")


@pytest.mark.asyncio
async def test_fake_audiodoc_can_delay_a_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delay a response long enough to exercise the real client timeout."""
    async with FakeAudiodoc() as server:
        _configure_bot_clients(monkeypatch, server)
        monkeypatch.setattr(config, "WHISPER_TIMEOUT", 0.01)
        server.set_behavior(
            "transcribe",
            FakeResponseOptions(delay=0.05),
        )

        with pytest.raises(WhisperTimeoutError, match="timed out"):
            await transcribe_audio(b"audio")


@pytest.mark.asyncio
async def test_fake_audiodoc_can_truncate_a_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Close a response before its declared content length is received."""
    async with FakeAudiodoc() as server:
        _configure_bot_clients(monkeypatch, server)
        server.set_behavior(
            "transcribe",
            FakeResponseOptions(truncated_body=True),
        )

        with pytest.raises(WhisperUnavailableError, match="connection error"):
            await transcribe_audio(b"audio")
