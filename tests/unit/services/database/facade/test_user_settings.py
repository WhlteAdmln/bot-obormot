# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the user settings operations of the database facade."""

import pytest

from bot_obormot.services.database import Database


@pytest.mark.asyncio
async def test_get_system_prompt_defaults_to_default_prompt(
    test_db: Database,
) -> None:
    user_id = 1618033
    prompt = await test_db.get_system_prompt(user_id)
    expected_text = test_db.settings.DEFAULT_SYSTEM_PROMPT
    assert prompt == expected_text, "a user without a prompt gets another prompt"


@pytest.mark.asyncio
async def test_set_system_prompt_stores_the_user_prompt(test_db: Database) -> None:
    user_id = 577215
    expected_text = "Новый промпт"
    await test_db.set_system_prompt(user_id, expected_text)
    prompt = await test_db.get_user_system_prompt(user_id)
    assert prompt == expected_text, "the stored user prompt differs from the one set"


@pytest.mark.asyncio
async def test_history_limit_defaults_to_default_value(test_db: Database) -> None:
    user_id = 2718281
    limit = await test_db.get_history_limit(user_id)
    expected_number = test_db.settings.DEFAULT_HISTORY_EXCHANGES
    assert limit == expected_number, "a user without a limit gets another limit"


@pytest.mark.asyncio
async def test_set_history_limit_stores_the_limit(test_db: Database) -> None:
    user_id = 99000111
    expected_number = 20
    await test_db.set_history_limit(user_id, expected_number)
    limit = await test_db.get_history_limit(user_id)
    assert limit == expected_number, "the stored limit differs from the one set"


@pytest.mark.asyncio
async def test_delete_history_limit_restores_the_default(test_db: Database) -> None:
    user_id = -4004
    await test_db.set_history_limit(user_id, 7)
    await test_db.delete_history_limit(user_id)
    limit = await test_db.get_history_limit(user_id)
    expected_number = test_db.settings.DEFAULT_HISTORY_EXCHANGES
    assert limit == expected_number, "the deleted limit is still used"


@pytest.mark.asyncio
async def test_set_history_limit_rejects_zero(test_db: Database) -> None:
    user_id = 13579
    number = 0
    with pytest.raises(ValueError, match="Invalid history limit") as excinfo:
        await test_db.set_history_limit(user_id, number)
    assert excinfo.type is ValueError, "zero was not rejected as a limit"


@pytest.mark.asyncio
async def test_set_history_limit_rejects_a_limit_above_the_maximum(
    test_db: Database,
) -> None:
    user_id = 24680
    number = test_db.settings.MAX_HISTORY_EXCHANGES + 1
    with pytest.raises(ValueError, match="Invalid history limit") as excinfo:
        await test_db.set_history_limit(user_id, number)
    assert excinfo.type is ValueError, "a too large limit was not rejected"
