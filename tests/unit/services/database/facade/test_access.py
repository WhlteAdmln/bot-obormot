# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the access operations of the database facade."""

import pytest

from bot_obormot.services.database import Database

USER_ID = 111111111

USER_A = 111111111

USER_B = 222222222

SUPERVISOR_ID = 999999999


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
async def test_blocked_users_repository_and_supervisor_protection(
    test_db: Database,
) -> None:
    """Blocked users repository and supervisor protection."""
    user_id = USER_ID + 100
    supervisor_id = 999999999

    assert await test_db.get_blocked_ids() == set()
    assert await test_db.block_user(user_id) is True
    assert await test_db.block_user(user_id) is False
    assert await test_db.get_blocked_ids() == {user_id}

    assert await test_db.block_user(supervisor_id) is False
    assert supervisor_id not in await test_db.get_blocked_ids()

    assert await test_db.unblock_user(user_id) is True
    assert await test_db.unblock_user(user_id) is False
    assert await test_db.get_blocked_ids() == set()
