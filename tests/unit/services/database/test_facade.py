# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for database facade."""

import asyncio
from collections import Counter
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from bot_obormot.services.database import (
    Database,
)
from tests.support.settings import make_settings


@pytest_asyncio.fixture(name="test_db")
async def fixture_test_db(
    tmp_path: Path,
) -> AsyncIterator[Database]:
    """Создаёт отдельную временную базу для тестов."""
    database_path = tmp_path / "test_database.db"

    settings = make_settings(
        DATABASE_PATH=str(database_path),
        SUPERVISOR_ID=999999999,
        ADMIN_IDS=set(),
        DEFAULT_SYSTEM_PROMPT="Тестовый стандартный промпт",
    )

    database = Database(settings)

    await database.connect()

    yield database

    await database.close()


async def _history_pairs(db: Database, user_id: int) -> list[tuple[str, object]]:
    """Return the stored history of a user as role and content pairs."""
    history = await db.get_history(user_id, limit=100)
    return [(message["role"], message["content"]) for message in history]


async def _write_exchanges(db: Database, user_id: int, count: int) -> None:
    """Store numbered exchanges for one user."""
    for number in range(count):
        await db.add_exchange(
            user_id,
            f"Сообщение {number}",
            f"Ответ {number}",
        )


@pytest.mark.asyncio
async def test_get_history_returns_only_the_first_users_exchange(
    test_db: Database,
) -> None:
    first_id = 111111111
    second_id = 222222222
    first_question = "Сообщение пользователя A"
    first_answer = "Ответ пользователю A"
    await test_db.add_exchange(first_id, first_question, first_answer)
    await test_db.add_exchange(
        second_id, "Сообщение пользователя B", "Ответ пользователю B"
    )
    expected = [("user", first_question), ("assistant", first_answer)]
    history = await _history_pairs(test_db, first_id)
    assert history == expected, "the first user's history holds foreign messages"


@pytest.mark.asyncio
async def test_get_history_returns_only_the_second_users_exchange(
    test_db: Database,
) -> None:
    first_id = 404040404
    second_id = 505050505
    second_question = "Вопрос второго пользователя"
    second_answer = "Ответ второму пользователю"
    await test_db.add_exchange(first_id, "Чужой вопрос", "Чужой ответ")
    await test_db.add_exchange(second_id, second_question, second_answer)
    expected = [("user", second_question), ("assistant", second_answer)]
    history = await _history_pairs(test_db, second_id)
    assert history == expected, "the second user's history holds foreign messages"


@pytest.mark.asyncio
async def test_set_system_prompt_stores_the_first_users_prompt(
    test_db: Database,
) -> None:
    first_id = 123456789
    first_prompt = "Персональный промпт A"
    await test_db.set_system_prompt(first_id, first_prompt)
    await test_db.set_system_prompt(987654321, "Персональный промпт B")
    prompt = await test_db.get_system_prompt(first_id)
    assert prompt == first_prompt, "another user's prompt replaced the first one"


@pytest.mark.asyncio
async def test_set_system_prompt_stores_the_second_users_prompt(
    test_db: Database,
) -> None:
    second_id = 246813579
    second_prompt = "Отвечай коротко и по делу"
    await test_db.set_system_prompt(135792468, "Отвечай подробно")
    await test_db.set_system_prompt(second_id, second_prompt)
    prompt = await test_db.get_system_prompt(second_id)
    assert prompt == second_prompt, "the second user's prompt was not stored"


@pytest.mark.asyncio
async def test_get_system_prompt_returns_default_for_user_without_prompt(
    test_db: Database,
) -> None:
    prompted_id = 314159265
    unprompted_id = 333333333
    default_prompt = "Тестовый стандартный промпт"
    await test_db.set_system_prompt(prompted_id, "Говори как пират")
    prompt = await test_db.get_system_prompt(unprompted_id)
    assert prompt == default_prompt, "a user without a prompt got a foreign prompt"


@pytest.mark.asyncio
async def test_delete_system_prompt_restores_the_default_prompt(
    test_db: Database,
) -> None:
    user_id = 271828182
    default_prompt = "Тестовый стандартный промпт"
    await test_db.set_system_prompt(user_id, "Персональный промпт для удаления")
    await test_db.delete_system_prompt(user_id)
    prompt = await test_db.get_system_prompt(user_id)
    assert prompt == default_prompt, "the deleted prompt did not fall back to default"


@pytest.mark.asyncio
async def test_delete_system_prompt_keeps_other_users_prompt(
    test_db: Database,
) -> None:
    deleted_id = 161803398
    kept_id = 141421356
    kept_prompt = "Персональный промпт B"
    await test_db.set_system_prompt(deleted_id, "Персональный промпт A")
    await test_db.set_system_prompt(kept_id, kept_prompt)
    await test_db.delete_system_prompt(deleted_id)
    prompt = await test_db.get_system_prompt(kept_id)
    assert prompt == kept_prompt, "deleting one prompt changed another user's prompt"


@pytest.mark.asyncio
async def test_reset_history_clears_the_users_history(test_db: Database) -> None:
    user_id = 172839405
    await test_db.add_exchange(user_id, "Что такое SQLite?", "Встроенная база данных")
    await test_db.reset_history(user_id)
    expected_empty: list[tuple[str, object]] = []
    history = await _history_pairs(test_db, user_id)
    assert history == expected_empty, "the reset history still holds messages"


@pytest.mark.asyncio
async def test_reset_history_keeps_other_users_history(test_db: Database) -> None:
    reset_id = 918273645
    kept_id = 564738291
    kept_question = "Сообщение пользователя B"
    kept_answer = "Ответ пользователю B"
    await test_db.add_exchange(reset_id, "Сообщение пользователя A", "Ответ A")
    await test_db.add_exchange(kept_id, kept_question, kept_answer)
    await test_db.reset_history(reset_id)
    expected = [("user", kept_question), ("assistant", kept_answer)]
    history = await _history_pairs(test_db, kept_id)
    assert history == expected, "resetting one history changed another user's history"


@pytest.mark.parametrize("position", [0, 1, 2])
@pytest.mark.asyncio
async def test_add_exchange_stores_concurrent_exchanges_of_each_user(
    test_db: Database,
    position: int,
) -> None:
    user_ids = (111111111, 222222222, 333333333)
    exchange_count = 10
    await asyncio.gather(
        *(_write_exchanges(test_db, user_id, exchange_count) for user_id in user_ids)
    )
    history = await test_db.get_history(user_ids[position], limit=100)
    roles = Counter(str(message["role"]) for message in history)
    expected_roles = Counter({"user": exchange_count, "assistant": exchange_count})
    assert roles == expected_roles, "concurrent writes lost or mixed up messages"
