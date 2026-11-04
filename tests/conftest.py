"""Общая конфигурация тестовой среды.

Переменные задаются до импорта bot.*: конфигурация приложения читается
непосредственно во время импорта модулей.
"""

import os


_TEST_ENV = {
    "BOT_TOKEN": "123456789:TEST_TOKEN_NOT_VALID",
    "SUPERVISOR_ID": "999999999",
    "ADMIN_IDS": "",
    "ALLOWED_USERS": "",
    "DATABASE_PATH": "data/test-bot.db",
    "LLM_BASE_URL": "http://127.0.0.1:8080/v1",
    "LLM_API_KEY": "test-key",
    "LLM_MODEL": "test-model",
    "LLM_TEMPERATURE": "0.7",
    "LLM_TOP_P": "0.9",
    "LLM_MAX_TOKENS": "2048",
    "LLM_TIMEOUT": "300",
    "LLM_MAX_CONCURRENT_GENERATIONS": "1",
    "MAX_HISTORY_EXCHANGES": "1000",
    "STREAM_UPDATE_INTERVAL": "1.0",
    "WHISPER_API_URL": "",
    "WHISPER_TIMEOUT": "180",
    "DOCUMENT_API_URL": "",
    "DOCUMENT_TIMEOUT": "300",
    "LOG_LEVEL": "WARNING",
}

for _name, _value in _TEST_ENV.items():
    if not os.environ.get(_name, "").strip():
        os.environ[_name] = _value

import pytest_asyncio


@pytest_asyncio.fixture
async def test_db(tmp_path, monkeypatch):
    """Создаёт изолированную SQLite-базу для тестов репозиториев.

    Фикстура расположена в conftest.py, чтобы быть доступной всем
    тестовым модулям, а не только test_database.py.
    """
    # Импорты выполняются после настройки тестовых переменных выше.
    from bot.config import config
    from bot.services.database import Database

    monkeypatch.setattr(
        config,
        "DATABASE_PATH",
        str(tmp_path / "history_test.db"),
    )
    monkeypatch.setattr(config, "SUPERVISOR_ID", 999999999)
    monkeypatch.setattr(config, "ADMIN_IDS", set())
    monkeypatch.setattr(config, "DEFAULT_SYSTEM_PROMPT", "Тестовый промпт")

    database = Database()
    await database.connect()

    try:
        yield database
    finally:
        await database.close()
