# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for chat pipeline."""

import pytest

from bot_obormot.errors import (
    LLMEmptyResponseError,
)
from bot_obormot.services.chat import pipeline as chat_pipeline
from tests.support.chat_pipeline import FakePipelineDatabase, FakePipelineLLM


async def _run(
    database: FakePipelineDatabase,
    llm: FakePipelineLLM,
    **options: object,
) -> str:
    return await chat_pipeline.process_chat(
        user_id=options.pop("user_id", 77),
        user_content="вход",
        saved_user_text=options.pop("saved_user_text", "вход"),
        dependencies=chat_pipeline.ChatPipelineDependencies(
            llm_client=llm,
            database=database,
        ),
        **options,
    )


@pytest.mark.asyncio
async def test_returns_the_joined_streamed_response() -> None:
    chunks = ["ответ", " готов"]
    expected = "ответ готов"
    result = await _run(FakePipelineDatabase(), FakePipelineLLM(chunks))
    assert result == expected, "the pipeline must join the streamed chunks"


@pytest.mark.asyncio
async def test_reports_the_accumulated_text_after_every_chunk() -> None:
    chunks = ["Ёж", " бежит"]
    updates: list[str] = []

    async def on_update(text: str) -> None:
        updates.append(text)

    await _run(FakePipelineDatabase(), FakePipelineLLM(chunks), on_update=on_update)
    expected = ["Ёж", "Ёж бежит"]
    assert updates == expected, "every update must carry the accumulated text"


@pytest.mark.asyncio
async def test_persists_the_saved_user_text_with_the_response_and_media() -> None:
    user_id = 4031
    saved = "сохранённый вход"
    media = [b"\x89PNG-bytes"]
    database = FakePipelineDatabase()
    await _run(
        database,
        FakePipelineLLM(["ответ"]),
        user_id=user_id,
        saved_user_text=saved,
        media=media,
    )
    expected = [("save", (user_id, saved, "ответ"), {"media": media})]
    assert database.calls_named("save") == expected, "the exchange must be saved"


@pytest.mark.asyncio
async def test_prunes_the_history_after_saving_the_exchange() -> None:
    user_id = 9182
    database = FakePipelineDatabase()
    await _run(database, FakePipelineLLM(["ответ"]), user_id=user_id)
    expected = ("prune", user_id)
    assert database.calls[-1] == expected, "pruning must follow the save"


@pytest.mark.asyncio
async def test_passes_the_fetched_history_to_the_llm() -> None:
    llm = FakePipelineLLM(["ответ"])
    await _run(FakePipelineDatabase(), llm)
    expected = [[[{"role": "user", "content": "old"}]]]
    assert llm.streamed == expected, "the fitted history must reach the stream"


@pytest.mark.asyncio
async def test_caps_the_history_limit_at_one_hundred() -> None:
    limit = 500
    database = FakePipelineDatabase(history_limit=limit)
    await _run(database, FakePipelineLLM(["ответ"]), user_id=13)
    expected = [("history", 13, 100)]
    assert database.calls_named("history") == expected, "the limit must be capped"


@pytest.mark.asyncio
async def test_keeps_a_history_limit_below_the_cap() -> None:
    limit = 17
    database = FakePipelineDatabase(history_limit=limit)
    await _run(database, FakePipelineLLM(["ответ"]), user_id=21)
    expected = [("history", 21, limit)]
    assert database.calls_named("history") == expected, "the limit must be kept"


@pytest.mark.asyncio
async def test_raises_on_an_empty_response() -> None:
    with pytest.raises(LLMEmptyResponseError, match="empty response"):
        await _run(FakePipelineDatabase(), FakePipelineLLM([" ", "\n"]))


@pytest.mark.asyncio
async def test_does_not_persist_an_empty_response() -> None:
    database = FakePipelineDatabase()
    with pytest.raises(LLMEmptyResponseError):
        await _run(database, FakePipelineLLM([]))
    assert not database.calls_named("save"), "an empty response must not be saved"


@pytest.mark.asyncio
async def test_returns_the_response_when_history_pruning_fails() -> None:
    failure = RuntimeError("prune failed on disk")
    database = FakePipelineDatabase(prune_error=failure)
    expected = "ответ"
    result = await _run(database, FakePipelineLLM([expected]))
    assert result == expected, "a pruning failure must not lose the response"
