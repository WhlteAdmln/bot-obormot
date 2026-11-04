import asyncio
import json
import logging
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
from bot.services.http_limits import read_limited_body


class FakeContent:
    def __init__(self, body: bytes):
        self._body = body

    async def iter_chunked(self, size):
        for start in range(0, len(self._body), size):
            yield self._body[start : start + size]


def json_body(payload) -> bytes:
    return json.dumps(payload).encode("utf-8")


@pytest.mark.asyncio
async def test_read_limited_body_rejects_declared_and_streamed_oversize():
    declared_oversize = SimpleNamespace(
        content_length=11,
        content=FakeContent(b"ignored"),
    )
    assert await read_limited_body(declared_oversize, 10) is None

    streamed_oversize = SimpleNamespace(
        content_length=None,
        content=FakeContent(b"12345678901"),
    )
    assert await read_limited_body(streamed_oversize, 10) is None

    within_limit = SimpleNamespace(
        content_length=None,
        content=FakeContent(b"1234567890"),
    )
    assert await read_limited_body(within_limit, 10) == b"1234567890"


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
async def test_transcribe_audio_posts_multipart_and_strips_result(monkeypatch, caplog):
    calls = {}

    class Response:
        status = 200
        content_length = None

        def __init__(self):
            self.content = FakeContent(json_body({"text": "  распознанный текст  "}))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class Session:
        def __init__(self, timeout, headers=None):
            calls["timeout"] = timeout
            calls["headers"] = headers

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, url, data):
            calls.update(url=url, data=data)
            return Response()

    monkeypatch.setattr(
        config, "WHISPER_API_URL", "http://whisper.test/transcribe?token=private"
    )
    monkeypatch.setattr(config, "WHISPER_TIMEOUT", 37)
    monkeypatch.setattr(config, "WHISPER_API_KEY", "")
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    with caplog.at_level(logging.INFO, logger="bot.services.audio.client"):
        result = await transcribe_audio(
            b"audio-bytes",
            "voice\nERROR forged.ogg",
        )

    assert result == "распознанный текст"
    assert calls["url"] == "http://whisper.test/transcribe?token=private"
    assert "распознанный текст" not in caplog.text
    assert "token=private" not in caplog.text
    assert r"filename=voice\nERROR forged.ogg" in caplog.text
    assert "\nERROR forged.ogg" not in caplog.text
    assert caplog.text.count("Whisper transcription received: 18 chars") == 1
    assert calls["timeout"].total == 37
    assert calls["headers"] == {}
    assert isinstance(calls["data"], aiohttp.FormData)
    multipart_filename = calls["data"]._fields[0][0]["filename"]
    assert multipart_filename == r"voice\nERROR forged.ogg"
    assert "\r" not in multipart_filename and "\n" not in multipart_filename


@pytest.mark.asyncio
async def test_transcribe_audio_sends_bearer_api_key(monkeypatch):
    calls = {}

    class Response:
        status = 200
        content_length = None
        content = FakeContent(json_body({"text": "recognized"}))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class Session:
        def __init__(self, timeout, headers=None):
            calls["headers"] = headers

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(config, "WHISPER_API_URL", "http://whisper.test")
    monkeypatch.setattr(config, "WHISPER_API_KEY", "whisper-secret")
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    assert await transcribe_audio(b"audio") == "recognized"
    assert calls["headers"] == {"Authorization": "Bearer whisper-secret"}


@pytest.mark.asyncio
async def test_transcribe_audio_rejects_oversized_response(monkeypatch):
    import bot.services.audio.client as audio_client

    monkeypatch.setattr(config, "WHISPER_API_URL", "http://whisper.test")
    monkeypatch.setattr(audio_client, "MAX_SERVICE_RESPONSE_BYTES", 10)

    class Response:
        status = 200
        content_length = None
        content = FakeContent(json_body({"text": "response is too long"}))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(aiohttp, "ClientSession", lambda **kwargs: Session())

    with pytest.raises(WhisperAPIError, match="response is too large"):
        await transcribe_audio(b"audio")


@pytest.mark.asyncio
async def test_transcribe_audio_preserves_api_empty_and_timeout_errors(monkeypatch):
    monkeypatch.setattr(config, "WHISPER_API_URL", "http://whisper.test")

    class Response:
        content_length = None

        def __init__(self, status=200, body=b'{"text": ""}'):
            self.status = status
            self.content = FakeContent(body)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

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
        lambda **kwargs: Session(Response(503, b"backend unavailable")),
    )
    with pytest.raises(WhisperAPIError, match="Whisper HTTP 503"):
        await transcribe_audio(b"audio")

    monkeypatch.setattr(
        aiohttp,
        "ClientSession",
        lambda **kwargs: Session(Response(body=json_body({"text": "  "}))),
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
    caplog,
):
    calls = {}

    class Response:
        status = 200
        content_length = None

        def __init__(self):
            self.content = FakeContent(
                json_body({"text": "Документ", "format": "pdf", "characters": 8})
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class Session:
        def __init__(self, timeout, headers=None):
            calls["timeout"] = timeout
            calls["headers"] = headers

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
    monkeypatch.setattr(config, "DOCUMENT_API_KEY", "")
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    with caplog.at_level(logging.INFO, logger="bot.services.documents.client"):
        result = await process_document(
            b"document-bytes",
            "../../report\nERROR forged.pdf",
        )

    assert result == {"text": "Документ", "format": "pdf", "characters": 8}
    assert r"filename=report\nERROR forged.pdf" in caplog.text
    assert "\nERROR forged.pdf" not in caplog.text
    assert calls["url"] == "http://documents.test/process"
    assert calls["timeout"].total == 61
    assert calls["headers"] == {}
    assert isinstance(calls["data"], aiohttp.FormData)
    multipart_filename = calls["data"]._fields[0][0]["filename"]
    assert multipart_filename == r"report\nERROR forged.pdf"
    assert "\r" not in multipart_filename and "\n" not in multipart_filename


@pytest.mark.asyncio
async def test_process_document_sends_bearer_api_key(monkeypatch):
    calls = {}

    class Response:
        status = 200
        content_length = None
        content = FakeContent(
            json_body({"text": "Text", "format": "pdf", "characters": 4})
        )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class Session:
        def __init__(self, timeout, headers=None):
            calls["headers"] = headers

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(config, "DOCUMENT_API_URL", "http://documents.test")
    monkeypatch.setattr(config, "DOCUMENT_API_KEY", "documents-secret")
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    await process_document(b"document", "file.pdf")
    assert calls["headers"] == {"Authorization": "Bearer documents-secret"}


@pytest.mark.asyncio
async def test_process_document_rejects_oversized_response(monkeypatch):
    import bot.services.documents.client as documents_client

    monkeypatch.setattr(config, "DOCUMENT_API_URL", "http://documents.test")
    monkeypatch.setattr(documents_client, "MAX_SERVICE_RESPONSE_BYTES", 10)

    class Response:
        status = 200
        content_length = None
        content = FakeContent(
            json_body(
                {
                    "text": "document response is too long",
                    "format": "pdf",
                    "characters": 29,
                }
            )
        )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(aiohttp, "ClientSession", lambda **kwargs: Session())

    with pytest.raises(DocumentAPIError) as error:
        await process_document(b"document", "file.pdf")

    assert error.value.status == 502
    assert error.value.detail == "Document Engine response is too large"


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
        content_length = None

        def __init__(self):
            self.content = FakeContent(b"unsupported file type")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

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
