# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm tokenizer."""

import os

import pytest

from bot.config.model import load_settings
from bot.services.llm import LLMClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_count_text_tokens() -> None:
    """Проверяет подсчёт токенов через работающий llama.cpp."""
    test_texts = [
        "Привет!",
        "Это проверка подсчёта токенов.",
        "Я улыбаюсь и смотрю на тебя. 😊",
        "Длинный текст " * 100,
    ]

    settings_environ = os.environ.copy()
    if not settings_environ.get("SUPERVISOR_ID", "").strip():
        settings_environ["SUPERVISOR_ID"] = "1"
    llm_client = LLMClient(load_settings(settings_environ))

    await llm_client.start()

    try:
        for text in test_texts:
            count = await llm_client.count_text_tokens(text)
            assert isinstance(count, int)
            assert count > 0
    finally:
        await llm_client.close()


@pytest.mark.asyncio
async def test_count_empty_text() -> None:
    """Пустой текст не должен отправляться на сервер."""
    llm_client = LLMClient()
    try:
        count = await llm_client.count_text_tokens("")
    finally:
        await llm_client.close()

    assert count == 0
