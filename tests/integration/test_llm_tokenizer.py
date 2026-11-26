# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm tokenizer."""

import os

import pytest

from bot_obormot.settings import load_settings
from tests.support.fake_llm import open_llm_client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_count_text_tokens() -> None:
    test_texts = [
        "Привет!",
        "Это проверка подсчёта токенов.",
        "Я улыбаюсь и смотрю на тебя. 😊",
        "Длинный текст " * 100,
    ]

    settings_environ = os.environ.copy()
    if not settings_environ.get("SUPERVISOR_ID", "").strip():
        settings_environ["SUPERVISOR_ID"] = "1"
    async with open_llm_client(load_settings(settings_environ)) as llm_client:
        await llm_client.start()
        counts = [await llm_client.count_text_tokens(text) for text in test_texts]

    assert all(count > 0 for count in counts), (
        f"token counts are not positive integers: {counts}"
    )


@pytest.mark.asyncio
async def test_count_empty_text() -> None:
    async with open_llm_client() as llm_client:
        count = await llm_client.count_text_tokens("")

    expected_count = 0
    assert count == expected_count, "empty text has tokens"
