# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for prompt handler."""

from dataclasses import replace

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import (
    DeleteMessage,
)

from tests.support.dispatcher import SETTINGS, AccessDatabase, feed_command, sent_texts
from tests.support.telegram import (
    FakeTelegramSession,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (555000000, None, "📄 Стандартный", "Тестовый системный промпт"),
        (
            555000001,
            "Мой персональный промпт",
            "👤 Персональный",
            "Мой персональный промпт",
        ),
    ],
)
async def test_prompt_command_shows_the_effective_prompt(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str | None, str, str],
) -> None:
    user_id, personal_prompt, source, effective_prompt = case
    if personal_prompt is not None:
        access_database.user_prompts[user_id] = personal_prompt

    session = await feed_command(dispatcher_runtime, user_id, "/prompt extra")

    expected_texts = [
        (
            "Текущий системный промпт\n"
            f"Источник: {source}\n\n"
            f"{effective_prompt}\n\n"
            "Изменить:\n"
            "/prompt_set\n\n"
            "Сбросить персональный промпт:\n"
            "/prompt_reset"
        )
    ]
    assert sent_texts(session) == expected_texts, "the effective prompt differs"


@pytest.mark.asyncio
async def test_prompt_command_truncates_a_long_effective_prompt(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    user_id = 555000002
    access_database.default_system_prompt = "x" * 3501

    session = await feed_command(dispatcher_runtime, user_id, "/prompt")

    displayed_prompt = "x" * 3500 + "\n\n... (промпт сокращён при отображении)"
    expected_texts = [
        (
            "Текущий системный промпт\n"
            "Источник: 📄 Стандартный\n\n"
            f"{displayed_prompt}\n\n"
            "Изменить:\n"
            "/prompt_set\n\n"
            "Сбросить персональный промпт:\n"
            "/prompt_reset"
        )
    ]
    assert sent_texts(session) == expected_texts, "the long prompt was not truncated"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_prompt_set_starts_the_input_flow(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    user_id = 555000003

    session = await feed_command(
        dispatcher_runtime,
        user_id,
        "/prompt_set extra arguments",
    )

    expected_texts = [
        (
            "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
            "Максимальная длина — 4000 символов.\n"
            "Для отмены используй /cancel."
        )
    ]
    assert sent_texts(session) == expected_texts, "the input flow did not start"


@pytest.mark.asyncio
async def test_prompt_save_persists_the_new_personal_prompt(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    user_id = 555000004
    new_prompt = "Новый системный промпт"
    await feed_command(dispatcher_runtime, user_id, "/prompt_set")

    await feed_command(dispatcher_runtime, user_id, new_prompt)

    stored_prompt = access_database.user_prompts[user_id]
    assert stored_prompt == new_prompt, "the personal prompt was not stored"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_prompt_save_confirms_the_new_personal_prompt(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    user_id = 555000013
    await feed_command(dispatcher_runtime, user_id, "/prompt_set")

    session = await feed_command(dispatcher_runtime, user_id, "Отвечай стихами")

    expected_texts = [
        (
            "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
            "Максимальная длина — 4000 символов.\n"
            "Для отмены используй /cancel."
        ),
        (
            "✅ Персональный системный промпт сохранён.\n\n"
            "Теперь он используется только в твоём чате."
        ),
    ]
    assert sent_texts(session) == expected_texts, "the save was not confirmed"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_prompt_save_deletes_the_input_messages(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    user_id = 555000014
    await feed_command(dispatcher_runtime, user_id, "/prompt_set")

    session = await feed_command(dispatcher_runtime, user_id, "Be terse, please.")

    expected_ids = [900, 1]
    deleted_ids = [
        request.message_id
        for request in session.requests
        if isinstance(request, DeleteMessage)
    ]
    assert deleted_ids == expected_ids, "the input messages were not deleted"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize(
    "case",
    [
        (555000005, "   ", "Промпт не может быть пустым. Попробуй ещё раз."),
        (
            555000006,
            "x" * 4001,
            "Промпт слишком длинный. Максимум 4000 символов.",
        ),
    ],
)
async def test_prompt_save_rejects_invalid_prompt_text(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    user_id, prompt_text, expected_text = case
    await feed_command(dispatcher_runtime, user_id, "/prompt_set")

    session = await feed_command(dispatcher_runtime, user_id, prompt_text)

    expected_texts = [
        (
            "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
            "Максимальная длина — 4000 символов.\n"
            "Для отмены используй /cancel."
        ),
        expected_text,
    ]
    assert sent_texts(session) == expected_texts, "the invalid prompt was accepted"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (
            555000007,
            None,
            "ℹ️ У тебя уже используется стандартный системный промпт.",
        ),
        (
            555000008,
            "Персональный промпт",
            (
                "🔄 Персональный системный промпт удалён.\n"
                "Теперь используется стандартный промпт."
            ),
        ),
    ],
)
async def test_prompt_reset_handles_personal_and_standard_prompts(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str | None, str],
) -> None:
    user_id, personal_prompt, expected_text = case
    if personal_prompt is not None:
        access_database.user_prompts[user_id] = personal_prompt

    session = await feed_command(
        dispatcher_runtime,
        user_id,
        "/prompt_reset extra",
    )

    expected_texts = [expected_text]
    assert sent_texts(session) == expected_texts, "the reset reply differs"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (555000015, None),
        (555000016, "Говори как пират"),
    ],
)
async def test_prompt_reset_removes_the_personal_prompt(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str | None],
) -> None:
    user_id, personal_prompt = case
    if personal_prompt is not None:
        access_database.user_prompts[user_id] = personal_prompt

    await feed_command(dispatcher_runtime, user_id, "/prompt_reset")

    assert user_id not in access_database.user_prompts, "a personal prompt remains"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_prompt_cancel_clears_the_input_flow(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    user_id = 555000009
    await feed_command(dispatcher_runtime, user_id, "/prompt_set")

    session = await feed_command(dispatcher_runtime, user_id, "/cancel extra")

    expected_texts = [
        (
            "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
            "Максимальная длина — 4000 символов.\n"
            "Для отмены используй /cancel."
        ),
        "❎ Ввод системного промпта отменён.",
    ]
    assert sent_texts(session) == expected_texts, "the input flow was not cancelled"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_prompt_cancel_deletes_the_input_messages(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    user_id = 555000017
    await feed_command(dispatcher_runtime, user_id, "/prompt_set")

    session = await feed_command(dispatcher_runtime, user_id, "/cancel")

    expected_ids = [900, 1]
    deleted_ids = [
        request.message_id
        for request in session.requests
        if isinstance(request, DeleteMessage)
    ]
    assert deleted_ids == expected_ids, "the input messages were not deleted"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failed_operation",
    ["get_user_system_prompt", "get_system_prompt"],
)
async def test_prompt_view_propagates_database_failures(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    failed_operation: str,
) -> None:
    user_id = 555000010
    access_database.scenario.failed_operation = failed_operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(dispatcher_runtime, user_id, "/prompt")

    expected_empty: list[str] = []
    sent = sent_texts(dispatcher_runtime[2])
    assert sent == expected_empty, "a reply was sent after a database failure"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        ("get_user_system_prompt", False),
        ("delete_system_prompt", True),
    ],
)
async def test_prompt_reset_propagates_database_failures(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[str, bool],
) -> None:
    failed_operation, has_personal_prompt = case
    user_id = 555000011
    if has_personal_prompt:
        access_database.user_prompts[user_id] = "Personal prompt"
    access_database.scenario.failed_operation = failed_operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(
            dispatcher_runtime,
            user_id,
            "/prompt_reset",
        )

    expected_empty: list[str] = []
    sent = sent_texts(dispatcher_runtime[2])
    assert sent == expected_empty, "a reply was sent after a database failure"


@pytest.mark.asyncio
async def test_prompt_save_propagates_database_failure(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    user_id = 555000012
    session = await feed_command(dispatcher_runtime, user_id, "/prompt_set")
    access_database.scenario.failed_operation = "set_system_prompt"

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(
            dispatcher_runtime,
            user_id,
            "New prompt",
        )

    expected_texts = [
        (
            "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
            "Максимальная длина — 4000 символов.\n"
            "Для отмены используй /cancel."
        )
    ]
    assert sent_texts(session) == expected_texts, "a save was reported after failure"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize(
    "case",
    [
        (555000020, "/prompt"),
        (555000021, "/prompt_set"),
        (555000022, "/prompt_reset"),
    ],
)
async def test_prompt_commands_are_denied_without_access(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str],
) -> None:
    user_id, command_text = case
    dispatcher_runtime[0].workflow_data["settings"] = replace(
        SETTINGS, ALLOW_ALL_USERS=False
    )

    session = await feed_command(dispatcher_runtime, user_id, command_text)

    expected_texts = ["⛔ У тебя нет доступа к этому боту."]
    assert sent_texts(session) == expected_texts, "a user without access was served"
