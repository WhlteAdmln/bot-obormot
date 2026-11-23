# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Общая конфигурация тестовой среды.

Настройки тестов создаются явно через tests.support.settings.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from bot_obormot.services.database import Database
from tests.support.settings import make_settings

_TEST_MARKERS = {"unit", "integration", "contract", "e2e"}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply test markers based on the top-level test directory."""
    tests_root = Path(__file__).resolve().parent

    for item in items:
        try:
            relative_path = item.path.resolve().relative_to(tests_root)
        except ValueError:
            continue

        if relative_path.parts and relative_path.parts[0] in _TEST_MARKERS:
            item.add_marker(relative_path.parts[0])


@pytest_asyncio.fixture(name="test_db")
async def fixture_test_db(
    tmp_path: Path,
) -> AsyncIterator["Database"]:
    """Создаёт изолированную SQLite-базу для тестов репозиториев.

    Фикстура расположена в conftest.py, чтобы быть доступной всем
    тестовым модулям, а не только test_database.py.
    """
    settings = make_settings(
        DATABASE_PATH=str(tmp_path / "history_test.db"),
        SUPERVISOR_ID=999999999,
        ADMIN_IDS=set(),
        DEFAULT_SYSTEM_PROMPT="Тестовый промпт",
    )

    database = Database(settings)
    await database.connect()

    try:
        yield database
    finally:
        await database.close()
