# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the user settings operations of the database facade."""

import pytest

from bot_obormot.services.database import Database
from tests.support.database_repositories import USER_ID


@pytest.mark.asyncio
async def test_facade_system_prompt_methods_preserve_default_behavior(
    test_db: Database,
) -> None:
    """Facade system prompt methods preserve default behavior."""
    assert (
        await test_db.get_system_prompt(USER_ID)
        == test_db.settings.DEFAULT_SYSTEM_PROMPT
    )
    await test_db.set_system_prompt(USER_ID, "Новый промпт")
    expected_text = "Новый промпт"
    assert await test_db.get_user_system_prompt(USER_ID) == expected_text


@pytest.mark.asyncio
async def test_history_limit_defaults_to_default_value(test_db: Database) -> None:
    """History limit defaults to default value."""
    assert (
        await test_db.get_history_limit(USER_ID)
        == test_db.settings.DEFAULT_HISTORY_EXCHANGES
    )


@pytest.mark.asyncio
async def test_set_and_delete_history_limit(test_db: Database) -> None:
    """Set and delete history limit."""
    await test_db.set_history_limit(USER_ID, 20)

    expected_number = 20
    assert await test_db.get_history_limit(USER_ID) == expected_number

    await test_db.delete_history_limit(USER_ID)

    assert (
        await test_db.get_history_limit(USER_ID)
        == test_db.settings.DEFAULT_HISTORY_EXCHANGES
    )


@pytest.mark.asyncio
async def test_history_limit_rejects_invalid_values(test_db: Database) -> None:
    """History limit rejects invalid values."""
    with pytest.raises(ValueError, match="Invalid history limit"):
        await test_db.set_history_limit(USER_ID, 0)

    with pytest.raises(ValueError, match="Invalid history limit"):
        await test_db.set_history_limit(
            USER_ID,
            test_db.settings.MAX_HISTORY_EXCHANGES + 1,
        )
