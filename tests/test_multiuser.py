# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for multiuser."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from bot.config import config
from bot.errors import DatabaseError
from bot.services.database import Database

USER_A = 111111111
USER_B = 222222222
USER_C = 333333333

SUPERVISOR_ID = 999999999


@pytest_asyncio.fixture
async def test_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Database]:
    """Создаёт отдельную временную базу для тестов."""
    database_path = tmp_path / "test_database.db"

    monkeypatch.setattr(
        config,
        "DATABASE_PATH",
        str(database_path),
    )

    monkeypatch.setattr(
        config,
        "SUPERVISOR_ID",
        SUPERVISOR_ID,
    )

    monkeypatch.setattr(
        config,
        "ADMIN_IDS",
        set(),
    )

    monkeypatch.setattr(
        config,
        "DEFAULT_SYSTEM_PROMPT",
        "Тестовый стандартный промпт",
    )

    database = Database()

    await database.connect()

    yield database

    await database.close()


@pytest.mark.asyncio
async def test_multiuser_isolation(test_db: Database) -> None:
    """Проверяет изоляцию истории и промптов пользователей."""
    db = test_db

    # Создаём отдельные истории.
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

    assert len(history_a) == 2
    assert len(history_b) == 2

    assert history_a[0]["content"] == "Сообщение пользователя A"
    assert history_b[0]["content"] == "Сообщение пользователя B"

    # Проверяем, что данные пользователей не смешиваются.
    assert all("пользователя B" not in str(message["content"]) for message in history_a)

    assert all("пользователя A" not in str(message["content"]) for message in history_b)

    # Сохраняем разные персональные промпты.
    await db.set_system_prompt(
        USER_A,
        "Персональный промпт A",
    )

    await db.set_system_prompt(
        USER_B,
        "Персональный промпт B",
    )

    assert await db.get_system_prompt(USER_A) == "Персональный промпт A"
    assert await db.get_system_prompt(USER_B) == "Персональный промпт B"

    # У пользователя C должен остаться стандартный промпт.
    assert await db.get_system_prompt(USER_C) == "Тестовый стандартный промпт"

    # Удаляем персональный промпт A.
    await db.delete_system_prompt(USER_A)

    assert await db.get_system_prompt(USER_A) == "Тестовый стандартный промпт"
    assert await db.get_system_prompt(USER_B) == "Персональный промпт B"

    # Очищаем историю A.
    await db.reset_history(USER_A)

    assert await db.get_history(USER_A, limit=20) == []

    # История B должна сохраниться.
    history_b = await db.get_history(USER_B, limit=20)

    assert len(history_b) == 2


@pytest.mark.asyncio
async def test_admin_management(test_db: Database) -> None:
    """Проверяет управление администраторами."""
    db = test_db

    # Сначала администраторов нет.
    assert await db.get_admin_ids() == set()

    # Добавляем администратора.
    assert await db.add_admin(USER_A) is True

    # Повторное добавление не должно создавать дубликат.
    assert await db.add_admin(USER_A) is False

    assert await db.get_admin_ids() == {USER_A}

    # Добавляем второго администратора.
    assert await db.add_admin(USER_B) is True

    assert await db.get_admin_ids() == {USER_A, USER_B}

    # Удаляем первого.
    assert await db.remove_admin(USER_A) is True

    assert await db.get_admin_ids() == {USER_B}

    # Повторное удаление возвращает False.
    assert await db.remove_admin(USER_A) is False

    # Supervisor нельзя добавить или удалить как обычного администратора.
    assert await db.add_admin(SUPERVISOR_ID) is False
    assert await db.remove_admin(SUPERVISOR_ID) is False


@pytest.mark.asyncio
async def test_concurrent_users(test_db: Database) -> None:
    """Проверяет параллельную запись нескольких пользователей."""
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

    # Каждый пользователь должен получить свои 20 сообщений.
    for user_id in (USER_A, USER_B, USER_C):
        history = await db.get_history(user_id, limit=100)

        assert len(history) == 20

        assert sum(message["role"] == "user" for message in history) == 10

        assert sum(message["role"] == "assistant" for message in history) == 10


@pytest.mark.asyncio
async def test_failed_exchange_rollback(test_db: Database) -> None:
    """Проверяет откат неудачного обмена и удаление изображения."""
    db = test_db

    image_data = b"fake-image-data"

    with pytest.raises(DatabaseError):
        await db.add_exchange(
            USER_A,
            "Тестовое сообщение",
            None,
            media=[image_data],
        )

    # Неудачный обмен не должен оставить сообщения.
    assert await db.get_history(USER_A, limit=20) == []

    # Неудачный обмен не должен оставить файлы изображений.
    remaining_files = list(db.images_dir.iterdir())

    assert remaining_files == []
