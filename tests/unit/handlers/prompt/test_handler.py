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

PROMPT_USER_ID = 555000000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (PROMPT_USER_ID, None, "📄 Стандартный", "Тестовый системный промпт"),
        (
            PROMPT_USER_ID + 1,
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

    assert sent_texts(session) == [
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


@pytest.mark.asyncio
async def test_prompt_command_truncates_a_long_effective_prompt(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    access_database.default_system_prompt = "x" * 3501

    session = await feed_command(
        dispatcher_runtime,
        PROMPT_USER_ID + 2,
        "/prompt",
    )

    displayed_prompt = "x" * 3500 + "\n\n... (промпт сокращён при отображении)"
    assert sent_texts(session) == [
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


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_prompt_set_starts_the_input_flow(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    session = await feed_command(
        dispatcher_runtime,
        PROMPT_USER_ID + 3,
        "/prompt_set extra arguments",
    )

    assert sent_texts(session) == [
        (
            "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
            "Максимальная длина — 4000 символов.\n"
            "Для отмены используй /cancel."
        )
    ]


@pytest.mark.asyncio
async def test_prompt_save_persists_the_new_personal_prompt(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    user_id = PROMPT_USER_ID + 4
    await feed_command(dispatcher_runtime, user_id, "/prompt_set")

    session = await feed_command(
        dispatcher_runtime,
        user_id,
        "Новый системный промпт",
    )

    expected_user_prompts = "Новый системный промпт"
    assert access_database.user_prompts[user_id] == expected_user_prompts
    assert sent_texts(session) == [
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
    deleted_ids = [
        request.message_id
        for request in session.requests
        if isinstance(request, DeleteMessage)
    ]
    assert deleted_ids == [900, 1]


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize(
    "case",
    [
        (PROMPT_USER_ID + 5, "   ", "Промпт не может быть пустым. Попробуй ещё раз."),
        (
            PROMPT_USER_ID + 6,
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

    assert sent_texts(session) == [
        (
            "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
            "Максимальная длина — 4000 символов.\n"
            "Для отмены используй /cancel."
        ),
        expected_text,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (
            PROMPT_USER_ID + 7,
            None,
            "ℹ️ У тебя уже используется стандартный системный промпт.",
        ),
        (
            PROMPT_USER_ID + 8,
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

    assert sent_texts(session) == [expected_text]
    assert user_id not in access_database.user_prompts


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_prompt_cancel_clears_the_input_flow(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    user_id = PROMPT_USER_ID + 9
    await feed_command(dispatcher_runtime, user_id, "/prompt_set")

    session = await feed_command(dispatcher_runtime, user_id, "/cancel extra")

    assert sent_texts(session) == [
        (
            "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
            "Максимальная длина — 4000 символов.\n"
            "Для отмены используй /cancel."
        ),
        "❎ Ввод системного промпта отменён.",
    ]
    deleted_ids = [
        request.message_id
        for request in session.requests
        if isinstance(request, DeleteMessage)
    ]
    assert deleted_ids == [900, 1]


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
    access_database.scenario.failed_operation = failed_operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(
            dispatcher_runtime,
            PROMPT_USER_ID + 10,
            "/prompt",
        )

    assert sent_texts(dispatcher_runtime[2]) == []


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
    user_id = PROMPT_USER_ID + 11
    if has_personal_prompt:
        access_database.user_prompts[user_id] = "Personal prompt"
    access_database.scenario.failed_operation = failed_operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(
            dispatcher_runtime,
            user_id,
            "/prompt_reset",
        )

    assert sent_texts(dispatcher_runtime[2]) == []


@pytest.mark.asyncio
async def test_prompt_save_propagates_database_failure(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    user_id = PROMPT_USER_ID + 12
    session = await feed_command(dispatcher_runtime, user_id, "/prompt_set")
    access_database.scenario.failed_operation = "set_system_prompt"

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(
            dispatcher_runtime,
            user_id,
            "New prompt",
        )

    assert sent_texts(session) == [
        (
            "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
            "Максимальная длина — 4000 символов.\n"
            "Для отмены используй /cancel."
        )
    ]


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize(
    "case",
    [
        (PROMPT_USER_ID + 20, "/prompt"),
        (PROMPT_USER_ID + 21, "/prompt_set"),
        (PROMPT_USER_ID + 22, "/prompt_reset"),
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

    assert sent_texts(session) == ["⛔ У тебя нет доступа к этому боту."]
