# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm tokenizer."""

import pytest

from bot.services.llm import llm_client


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
    count = await llm_client.count_text_tokens("")

    assert count == 0
