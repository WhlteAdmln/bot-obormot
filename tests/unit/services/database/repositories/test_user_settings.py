# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for repositories user settings."""

import aiosqlite
import pytest

from bot_obormot.services.database import Database
from bot_obormot.services.database.repositories import (
    user_settings,
)


@pytest.fixture(name="connection")
def fixture_connection(test_db: Database) -> aiosqlite.Connection:
    """Return the open connection of the test database."""
    if test_db.connection is None:
        message = "the test database has no open connection"
        raise RuntimeError(message)
    return test_db.connection


@pytest.mark.asyncio
async def test_get_system_prompt_returns_none_without_a_prompt(
    connection: aiosqlite.Connection,
) -> None:
    user_id = 48151623
    prompt = await user_settings.get_system_prompt(connection, user_id)
    assert prompt is None, "a user without a prompt has a stored prompt"


@pytest.mark.asyncio
async def test_set_system_prompt_stores_the_prompt(
    connection: aiosqlite.Connection,
) -> None:
    user_id = 90210
    expected_text = "Персональный промпт"
    await user_settings.set_system_prompt(connection, user_id, expected_text)
    prompt = await user_settings.get_system_prompt(connection, user_id)
    assert prompt == expected_text, "the stored prompt differs from the one set"


@pytest.mark.asyncio
async def test_delete_system_prompt_removes_the_prompt(
    connection: aiosqlite.Connection,
) -> None:
    user_id = -100777
    text = "Отвечай коротко, по делу"
    await user_settings.set_system_prompt(connection, user_id, text)
    await user_settings.delete_system_prompt(connection, user_id)
    prompt = await user_settings.get_system_prompt(connection, user_id)
    assert prompt is None, "the deleted prompt is still stored"
