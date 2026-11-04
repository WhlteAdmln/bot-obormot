import asyncio
from types import SimpleNamespace

import aiohttp
import pytest

from bot.config import config
from bot.errors import (
    DocumentAPIError,
    DocumentUnavailableError,
    MediaError,
    WhisperAPIError,
    WhisperEmptyAudioError,
    WhisperTimeoutError,
    WhisperUnavailableError,
)
from bot.services.audio import (
    MAX_AUDIO_DURATION,
    get_audio_info,
    transcribe_audio,
    validate_audio_duration,
)
from bot.services.documents import process_document
from bot.services.documents.response import validate_document_response


def make_message(**values):
    defaults = {"voice": None, "audio": None, "video_note": None}
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_get_audio_info_preserves_voice_audio_and_video_note_names():
    assert get_audio_info(make_message(voice=SimpleNamespace(file_id="voice-id"))) == (
        "voice-id",
        "voice.ogg",
    )
    assert get_audio_info(
        make_message(audio=SimpleNamespace(file_id="audio-id", file_name="track.wav"))
    ) == ("audio-id", "track.wav")
    assert get_audio_info(
        make_message(audio=SimpleNamespace(file_id="audio-id", file_name=None))
    ) == ("audio-id", "audio.mp3")
    assert get_audio_info(
        make_message(video_note=SimpleNamespace(file_id="note-id"))
    ) == ("note-id", "video_note.mp4")
    assert get_audio_info(make_message()) == (None, None)


def test_validate_audio_duration_keeps_five_minute_boundary():
    assert MAX_AUDIO_DURATION == 300
    validate_audio_duration(make_message(voice=SimpleNamespace(duration=300)))
    with pytest.raises(MediaError, match="Аудиофайл слишком длинный"):
        validate_audio_duration(make_message(voice=SimpleNamespace(duration=301)))


def test_validate_audio_duration_checks_audio_and_video_note():
    with pytest.raises(MediaError):
        validate_audio_duration(make_message(audio=SimpleNamespace(duration=301)))
    with pytest.raises(MediaError):
        validate_audio_duration(make_message(video_note=SimpleNamespace(duration=301)))


@pytest.mark.asyncio
async def test_transcribe_audio_rejects_missing_whisper_url(monkeypatch):
    monkeypatch.setattr(config, "WHISPER_API_URL", "")
    with pytest.raises(WhisperUnavailableError, match="not configured"):
        await transcribe_audio(b"audio")


@pytest.mark.asyncio
async def test_transcribe_audio_posts_multipart_and_strips_result(monkeypatch):
    calls = {}

    class Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def json(self):
            return {"text": "  распознанный текст  "}

    class Session:
        def __init__(self, timeout):
            calls["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, url, data):
            calls.update(url=url, data=data)
            return Response()

    monkeypatch.setattr(config, "WHISPER_API_URL", "http://whisper.test/transcribe")
    monkeypatch.setattr(config, "WHISPER_TIMEOUT", 37)
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    result = await transcribe_audio(b"audio-bytes", "voice.ogg")

    assert result == "распознанный текст"
    assert calls["url"] == "http://whisper.test/transcribe"
    assert calls["timeout"].total == 37
    assert isinstance(calls["data"], aiohttp.FormData)


@pytest.mark.asyncio
async def test_transcribe_audio_preserves_api_empty_and_timeout_errors(monkeypatch):
    monkeypatch.setattr(config, "WHISPER_API_URL", "http://whisper.test")

    class Response:
        def __init__(self, status=200, text="", payload=None):
            self.status = status
            self._text = text
            self._payload = payload or {"text": ""}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def text(self):
            return self._text

        async def json(self):
            return self._payload

    class Session:
        def __init__(self, response):
            self.response = response

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return self.response

    monkeypatch.setattr(
        aiohttp,
        "ClientSession",
        lambda **kwargs: Session(Response(503, "backend unavailable")),
    )
    with pytest.raises(WhisperAPIError, match="Whisper HTTP 503"):
        await transcribe_audio(b"audio")

    monkeypatch.setattr(
        aiohttp,
        "ClientSession",
        lambda **kwargs: Session(Response(payload={"text": "  "})),
    )
    with pytest.raises(WhisperEmptyAudioError):
        await transcribe_audio(b"audio")

    def timeout_session(**kwargs):
        raise asyncio.TimeoutError

    monkeypatch.setattr(aiohttp, "ClientSession", timeout_session)
    with pytest.raises(WhisperTimeoutError):
        await transcribe_audio(b"audio")


def test_validate_document_response_accepts_valid_payload_without_copying():
    payload = {"text": "Текст", "format": "pdf", "characters": 5}
    assert validate_document_response(payload) is payload


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ([], "Invalid response from Document Engine"),
        ({"format": "pdf", "characters": 1}, "invalid text"),
        ({"text": "x", "characters": 1}, "invalid format"),
        ({"text": "x", "format": "pdf"}, "invalid character count"),
    ],
)
def test_validate_document_response_rejects_invalid_payloads(payload, detail):
    with pytest.raises(DocumentAPIError, match=detail):
        validate_document_response(payload)


@pytest.mark.asyncio
async def test_process_document_preserves_filename_sanitization_and_response(
    monkeypatch,
):
    calls = {}

    class Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def json(self):
            return {"text": "Документ", "format": "pdf", "characters": 8}

    class Session:
        def __init__(self, timeout):
            calls["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, url, data):
            calls["url"] = url
            calls["data"] = data
            return Response()

    monkeypatch.setattr(config, "DOCUMENT_API_URL", "http://documents.test/process")
    monkeypatch.setattr(config, "DOCUMENT_TIMEOUT", 61)
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    result = await process_document(b"document-bytes", "../../report.pdf")

    assert result == {"text": "Документ", "format": "pdf", "characters": 8}
    assert calls["url"] == "http://documents.test/process"
    assert calls["timeout"].total == 61
    assert isinstance(calls["data"], aiohttp.FormData)


@pytest.mark.asyncio
async def test_process_document_rejects_missing_url_and_preserves_http_status(
    monkeypatch,
):
    monkeypatch.setattr(config, "DOCUMENT_API_URL", "")
    with pytest.raises(DocumentUnavailableError, match="not configured"):
        await process_document(b"data", "file.pdf")

    monkeypatch.setattr(config, "DOCUMENT_API_URL", "http://documents.test")

    class Response:
        status = 415

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def text(self):
            return "unsupported file type"

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(aiohttp, "ClientSession", lambda **kwargs: Session())
    with pytest.raises(DocumentAPIError) as error:
        await process_document(b"data", "file.pdf")
    assert error.value.status == 415
    assert error.value.detail == "unsupported file type"


@pytest.mark.asyncio
async def test_process_document_maps_timeout_and_connection_errors(monkeypatch):
    monkeypatch.setattr(config, "DOCUMENT_API_URL", "http://documents.test")

    def timeout_session(**kwargs):
        raise asyncio.TimeoutError

    monkeypatch.setattr(aiohttp, "ClientSession", timeout_session)
    from bot.errors import DocumentTimeoutError

    with pytest.raises(DocumentTimeoutError, match="timed out"):
        await process_document(b"data", "file.pdf")

    def failed_session(**kwargs):
        raise aiohttp.ClientConnectionError("connection refused")

    monkeypatch.setattr(aiohttp, "ClientSession", failed_session)
    with pytest.raises(DocumentUnavailableError, match="connection error"):
        await process_document(b"data", "file.pdf")
