# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for database facade."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from bot_obormot.services.database import (
    Database,
)
from tests.support.settings import make_settings

USER_A = 111111111


USER_B = 222222222


USER_C = 333333333


SUPERVISOR_ID = 999999999


@pytest_asyncio.fixture(name="test_db")
async def fixture_test_db(
    tmp_path: Path,
) -> AsyncIterator[Database]:
    """Создаёт отдельную временную базу для тестов."""
    database_path = tmp_path / "test_database.db"

    settings = make_settings(
        DATABASE_PATH=str(database_path),
        SUPERVISOR_ID=SUPERVISOR_ID,
        ADMIN_IDS=set(),
        DEFAULT_SYSTEM_PROMPT="Тестовый стандартный промпт",
    )

    database = Database(settings)

    await database.connect()

    yield database

    await database.close()


@pytest.mark.asyncio
async def test_keeps_histories_and_prompts_of_users_apart(test_db: Database) -> None:
    db = test_db

    await db.add_exchange(
        USER_A,
        "Сообщение пользователя A",
        "Ответ пользователю A",
    )

    await db.add_exchange(
        USER_B,
        "Сообщение пользователя B",
        "Ответ пользователю B",
    )

    history_a = await db.get_history(USER_A, limit=20)
    history_b = await db.get_history(USER_B, limit=20)

    expected_count = 2
    assert len(history_a) == expected_count
    expected_count = 2
    assert len(history_b) == expected_count

    expected_content = "Сообщение пользователя A"
    assert history_a[0]["content"] == expected_content
    expected_content = "Сообщение пользователя B"
    assert history_b[0]["content"] == expected_content

    other_user_text = "пользователя B"
    assert all(other_user_text not in str(message["content"]) for message in history_a)

    other_user_text = "пользователя A"
    assert all(other_user_text not in str(message["content"]) for message in history_b)

    await db.set_system_prompt(
        USER_A,
        "Персональный промпт A",
    )

    await db.set_system_prompt(
        USER_B,
        "Персональный промпт B",
    )

    expected_text = "Персональный промпт A"
    assert await db.get_system_prompt(USER_A) == expected_text
    expected_text = "Персональный промпт B"
    assert await db.get_system_prompt(USER_B) == expected_text

    expected_text = "Тестовый стандартный промпт"
    assert await db.get_system_prompt(USER_C) == expected_text

    await db.delete_system_prompt(USER_A)

    expected_text = "Тестовый стандартный промпт"
    assert await db.get_system_prompt(USER_A) == expected_text
    expected_text = "Персональный промпт B"
    assert await db.get_system_prompt(USER_B) == expected_text

    await db.reset_history(USER_A)

    assert await db.get_history(USER_A, limit=20) == []

    history_b = await db.get_history(USER_B, limit=20)

    expected_count = 2
    assert len(history_b) == expected_count


@pytest.mark.asyncio
async def test_stores_concurrent_exchanges_of_several_users(test_db: Database) -> None:
    db = test_db

    async def write_messages(user_id: int) -> None:
        for number in range(10):
            await db.add_exchange(
                user_id,
                f"Сообщение {number}",
                f"Ответ {number}",
            )

    await asyncio.gather(
        write_messages(USER_A),
        write_messages(USER_B),
        write_messages(USER_C),
    )

    for user_id in (USER_A, USER_B, USER_C):
        history = await db.get_history(user_id, limit=100)

        expected_count = 20
        assert len(history) == expected_count

        expected_sum = 10
        expected_role = "user"
        assert (
            sum(message["role"] == expected_role for message in history) == expected_sum
        )

        expected_sum = 10
        expected_role = "assistant"
        assert (
            sum(message["role"] == expected_role for message in history) == expected_sum
        )
