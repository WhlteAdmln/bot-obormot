import pytest
import pytest_asyncio

from bot.config import config
from bot.services.database import Database


USER_ID = 111111111


@pytest_asyncio.fixture
async def test_db(tmp_path, monkeypatch):
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


@pytest.mark.asyncio
async def test_history_limit_defaults_to_default_value(test_db):
    assert await test_db.get_history_limit(USER_ID) == config.DEFAULT_HISTORY_EXCHANGES


@pytest.mark.asyncio
async def test_set_and_delete_history_limit(test_db):
    await test_db.set_history_limit(USER_ID, 20)

    assert await test_db.get_history_limit(USER_ID) == 20

    await test_db.delete_history_limit(USER_ID)

    assert await test_db.get_history_limit(USER_ID) == config.DEFAULT_HISTORY_EXCHANGES


@pytest.mark.asyncio
async def test_history_limit_rejects_invalid_values(test_db):
    with pytest.raises(ValueError):
        await test_db.set_history_limit(USER_ID, 0)

    with pytest.raises(ValueError):
        await test_db.set_history_limit(
            USER_ID,
            config.MAX_HISTORY_EXCHANGES + 1,
        )


@pytest.mark.asyncio
async def test_history_limit_counts_complete_exchanges(test_db):
    for number in range(5):
        await test_db.add_exchange(
            USER_ID,
            f"Вопрос {number}",
            f"Ответ {number}",
        )

    history = await test_db.get_history(USER_ID, limit=2)

    assert len(history) == 4

    assert [item["content"] for item in history] == [
        "Вопрос 3",
        "Ответ 3",
        "Вопрос 4",
        "Ответ 4",
    ]


@pytest.mark.asyncio
async def test_history_limit_zero_returns_empty_history(test_db):
    await test_db.add_exchange(
        USER_ID,
        "Вопрос",
        "Ответ",
    )

    assert await test_db.get_history(USER_ID, limit=0) == []


@pytest.mark.asyncio
async def test_history_ignores_incomplete_messages(test_db):
    await test_db.add_exchange(
        USER_ID,
        "Вопрос 1",
        "Ответ 1",
    )

    await test_db.add_message(
        USER_ID,
        "user",
        "Незавершённый вопрос",
    )

    history = await test_db.get_history(USER_ID, limit=10)

    assert len(history) == 2

    assert [item["content"] for item in history] == [
        "Вопрос 1",
        "Ответ 1",
    ]


@pytest.mark.asyncio
async def test_history_limit_isolated_between_users(test_db):
    await test_db.set_history_limit(USER_ID, 10)
    await test_db.set_history_limit(USER_ID + 1, 5)

    assert await test_db.get_history_limit(USER_ID) == 10
    assert await test_db.get_history_limit(USER_ID + 1) == 5

    assert (
        await test_db.get_history_limit(USER_ID + 2) == config.DEFAULT_HISTORY_EXCHANGES
    )
