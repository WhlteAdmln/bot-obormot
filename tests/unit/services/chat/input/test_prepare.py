# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input prepare."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot_obormot.services.chat.input import (
    MessageInfo,
    PreparedMessage,
    prepare_message,
)
from bot_obormot.services.chat.input import prepare as pipeline_module
from tests.support.message_input import make_message
from tests.support.settings import make_settings


@pytest.mark.asyncio
async def test_prepare_message_preserves_processing_order_and_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prepare message preserves processing order and result."""
    events = []
    app_settings = make_settings()
    info = MessageInfo(
        file_id="image-id",
        media_type="image",
        audio_file_id="voice-id",
        audio_filename="voice.ogg",
        document=SimpleNamespace(file_id="doc-id", file_name="report.pdf"),
        has_media=True,
        has_audio=True,
        has_document=True,
        has_text=False,
    )
    image_bytes = [b"image-bytes"]

    async def prepare_audio(
        _message: object,
        _info: object,
        *,
        settings: object,
    ) -> str:
        assert settings is app_settings
        events.append("audio")
        return "Распознано"

    async def prepare_media(_message: object, _info: object) -> tuple[object, ...]:
        events.append("media")
        return ["data:image/jpeg;base64,AA=="], image_bytes

    async def prepare_document(
        _message: object,
        _info: object,
        *,
        settings: object,
    ) -> tuple[object, ...]:
        assert settings is app_settings
        events.append("document")
        return "Текст документа", "pdf"

    def build_content(_message: object, _info: object, **kwargs: object) -> str:
        events.append("content")
        assert kwargs["transcribed_text"] == "Распознано"
        assert kwargs["image_urls"] == ["data:image/jpeg;base64,AA=="]
        assert kwargs["document_text"] == "Текст документа"
        assert "document_format" not in kwargs
        return "Содержимое для LLM"

    def build_history(_message: object, _info: object, **kwargs: object) -> str:
        events.append("history")
        assert kwargs["document_format"] == "pdf"
        return "Текст для истории"

    monkeypatch.setattr(pipeline_module, "prepare_audio", prepare_audio)
    monkeypatch.setattr(pipeline_module, "prepare_media", prepare_media)
    monkeypatch.setattr(pipeline_module, "prepare_document", prepare_document)
    monkeypatch.setattr(pipeline_module, "build_user_content", build_content)
    monkeypatch.setattr(pipeline_module, "build_saved_user_text", build_history)

    result = await prepare_message(
        make_message(),
        info,
        text_override=None,
        settings=app_settings,
    )

    assert events == ["audio", "media", "document", "content", "history"]
    assert result == PreparedMessage(
        user_content="Содержимое для LLM",
        saved_user_text="Текст для истории",
        image_bytes=image_bytes,
    )
