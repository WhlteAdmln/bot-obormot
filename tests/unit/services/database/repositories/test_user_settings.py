# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for repositories user settings."""

import pytest

from bot_obormot.services.database import Database
from bot_obormot.services.database.repositories import (
    user_settings,
)
from tests.support.database_repositories import USER_ID


@pytest.mark.asyncio
async def test_sets_reads_and_deletes_system_prompt(test_db: Database) -> None:
    assert await user_settings.get_system_prompt(test_db.connection, USER_ID) is None

    await user_settings.set_system_prompt(
        test_db.connection,
        USER_ID,
        "Персональный промпт",
    )
    expected_text = "Персональный промпт"
    assert (
        await user_settings.get_system_prompt(test_db.connection, USER_ID)
        == expected_text
    )

    await user_settings.delete_system_prompt(test_db.connection, USER_ID)
    assert await user_settings.get_system_prompt(test_db.connection, USER_ID) is None
