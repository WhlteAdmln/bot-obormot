# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Exercise handlers through the real Dispatcher."""

from collections.abc import AsyncIterator
from dataclasses import replace

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import (
    DeleteMessage,
    EditMessageText,
    GetMe,
    SendMessage,
    SetMyCommands,
)
from aiogram.types import User

from bot.app.routers import configure_dispatcher
from bot.middlewares.throttle import ThrottleMiddleware
from tests.support.settings import make_settings
from tests.support.telegram import (
    FakeTelegramSession,
    make_message,
    make_update,
)

SUPERVISOR_ID = 999999999
ADMIN_ID = 111111111
USER_ID = 222222222
OUTSIDER_ID = 333333333
HISTORY_USER_ID = 444000000
HISTORY_ADMIN_ID = 444000001
HISTORY_TARGET_ID = 444000002
PROMPT_USER_ID = 555000000
PROMPT_USER_ID_2 = 555000001
PROMPT_USER_ID_3 = 555000002

SETTINGS = make_settings(SUPERVISOR_ID=SUPERVISOR_ID, ALLOW_ALL_USERS=True)


class _AccessDatabase:
    """Provide deterministic database responses for dispatcher tests."""

    def __init__(self, admin_ids: set[int] | None = None) -> None:
        self.admin_ids = set(admin_ids or ())
        self.history_limits: dict[int, int] = {}
        self.reset_history_calls: list[int] = []
        self.forgotten_user_ids: list[int] = []
        self.set_history_limit_calls: list[tuple[int, int]] = []
        self.blocked_user_ids: set[int] = set()
        self.add_admin_calls: list[int] = []
        self.remove_admin_calls: list[int] = []
        self.block_user_calls: list[int] = []
        self.unblock_user_calls: list[int] = []
        self.add_admin_result = True
        self.remove_admin_result = True
        self.block_user_result = True
        self.unblock_user_result = True
        self.user_prompts: dict[int, str] = {}
        self.default_system_prompt = "Тестовый системный промпт"
        self.failed_operation: str | None = None
        self.admin_lookup_calls = 0
        self.fail_admin_lookup_on: int | None = None

    async def get_blocked_ids(self) -> set[int]:
        """Return configured blocked users."""
        self._check_failure("get_blocked_ids")
        return self.blocked_user_ids

    async def get_admin_ids(self) -> set[int]:
        """Return configured administrator IDs."""
        self.admin_lookup_calls += 1
        if self.admin_lookup_calls == self.fail_admin_lookup_on:
            msg = "database unavailable"
            raise RuntimeError(msg)
        self._check_failure("get_admin_ids")
        return self.admin_ids

    def _check_failure(self, operation: str) -> None:
        if self.failed_operation == operation:
            msg = "database unavailable"
            raise RuntimeError(msg)

    async def reset_history(self, user_id: int) -> None:
        """Record a dialog history reset."""
        self._check_failure("reset_history")
        self.reset_history_calls.append(user_id)

    async def forget_user(self, user_id: int) -> None:
        """Record a complete user data deletion."""
        self._check_failure("forget_user")
        self.forgotten_user_ids.append(user_id)

    async def get_history_limit(self, user_id: int) -> int:
        """Return the configured history limit or a test default."""
        self._check_failure("get_history_limit")
        return self.history_limits.get(user_id, 17)

    async def set_history_limit(self, user_id: int, limit: int) -> None:
        """Record and store a history limit."""
        self._check_failure("set_history_limit")
        self.history_limits[user_id] = limit
        self.set_history_limit_calls.append((user_id, limit))

    async def get_user_system_prompt(self, user_id: int) -> str | None:
        """Return a user's personal system prompt."""
        self._check_failure("get_user_system_prompt")
        return self.user_prompts.get(user_id)

    async def get_system_prompt(self, user_id: int) -> str:
        """Return the effective system prompt."""
        self._check_failure("get_system_prompt")
        return self.user_prompts.get(user_id, self.default_system_prompt)

    async def set_system_prompt(self, user_id: int, prompt: str) -> None:
        """Store a user's personal system prompt."""
        self._check_failure("set_system_prompt")
        self.user_prompts[user_id] = prompt

    async def delete_system_prompt(self, user_id: int) -> None:
        """Remove a user's personal system prompt."""
        self._check_failure("delete_system_prompt")
        self.user_prompts.pop(user_id, None)

    async def health_check(self) -> bool:
        """Return a successful database health check."""
        self._check_failure("health_check")
        return True

    async def add_admin(self, user_id: int) -> bool:
        """Record an administrator addition."""
        self._check_failure("add_admin")
        self.add_admin_calls.append(user_id)
        if self.add_admin_result:
            self.admin_ids.add(user_id)
        return self.add_admin_result

    async def remove_admin(self, user_id: int) -> bool:
        """Record an administrator removal."""
        self._check_failure("remove_admin")
        self.remove_admin_calls.append(user_id)
        if self.remove_admin_result:
            self.admin_ids.discard(user_id)
        return self.remove_admin_result

    async def block_user(self, user_id: int) -> bool:
        """Record a user block."""
        self._check_failure("block_user")
        self.block_user_calls.append(user_id)
        if self.block_user_result:
            self.blocked_user_ids.add(user_id)
        return self.block_user_result

    async def unblock_user(self, user_id: int) -> bool:
        """Record a user unblock."""
        self._check_failure("unblock_user")
        self.unblock_user_calls.append(user_id)
        if self.unblock_user_result:
            self.blocked_user_ids.discard(user_id)
        return self.unblock_user_result


class _FakeLLM:
    """Provide an offline LLM health-check response."""

    def __init__(self, result: tuple[bool, str] = (True, "Доступен")) -> None:
        self.result = result

    async def health_check(self) -> tuple[bool, str]:
        """Return the configured LLM health status."""
        return self.result


class _FailingAdminDatabase:
    """Simulate an administrator lookup failure in the start handler."""

    def __init__(self) -> None:
        self.admin_lookup_calls = 0

    async def get_blocked_ids(self) -> set[int]:
        """Return no blocked users for the access middleware."""
        return set()

    async def get_admin_ids(self) -> set[int]:
        """Raise an error when administrator IDs are requested."""
        self.admin_lookup_calls += 1
        if self.admin_lookup_calls == 1:
            return set()
        msg = "database unavailable"
        raise RuntimeError(msg)


def _reset_throttle(dispatcher: Dispatcher) -> None:
    """Reset rate-limit state between isolated dispatcher tests."""
    routers: list[Router] = [dispatcher]
    while routers:
        router = routers.pop()
        for observer in router.observers.values():
            for manager in (observer.outer_middleware, observer.middleware):
                for middleware in getattr(manager, "_middlewares", ()):
                    if isinstance(middleware, ThrottleMiddleware):
                        middleware._events.clear()
        routers.extend(router.sub_routers)


@pytest.fixture
def access_database(
    dispatcher: Dispatcher,
) -> _AccessDatabase:
    """Configure an isolated database and open access for dispatcher tests."""
    database = _AccessDatabase()
    dispatcher.workflow_data["settings"] = SETTINGS
    dispatcher.workflow_data["llm_client"] = _FakeLLM()
    dispatcher.workflow_data["database"] = database
    return database


@pytest.fixture(scope="module")
def dispatcher() -> Dispatcher:
    """Create one configured dispatcher for the test module."""
    return configure_dispatcher(Dispatcher(storage=MemoryStorage()), SETTINGS)


@pytest_asyncio.fixture
async def dispatcher_runtime(
    dispatcher: Dispatcher,
    access_database: _AccessDatabase,
) -> AsyncIterator[tuple[Dispatcher, Bot, FakeTelegramSession]]:
    """Create a fake Telegram API session for one dispatcher update."""
    assert isinstance(access_database, _AccessDatabase)
    assert dispatcher.workflow_data["settings"] is SETTINGS
    _reset_throttle(dispatcher)
    session = FakeTelegramSession(
        {
            DeleteMessage: True,
            EditMessageText: True,
            GetMe: User(id=900, is_bot=True, first_name="Test Bot"),
            SendMessage: make_message(message_id=900),
            SetMyCommands: True,
        }
    )
    bot = Bot(token=SETTINGS.BOT_TOKEN, session=session)

    try:
        yield dispatcher, bot, session
    finally:
        await bot.session.close()


def _sent_texts(session: FakeTelegramSession) -> list[str]:
    """Extract text fields from outgoing SendMessage requests."""
    return [
        request.text for request in session.requests if isinstance(request, SendMessage)
    ]


def _sent_command_names(session: FakeTelegramSession) -> set[str]:
    """Extract command names from the outgoing SetMyCommands request."""
    requests = [
        request for request in session.requests if isinstance(request, SetMyCommands)
    ]
    assert len(requests) == 1
    return {command.command for command in requests[0].commands}


def _edited_texts(session: FakeTelegramSession) -> list[str]:
    """Extract text fields from outgoing EditMessageText requests."""
    return [
        request.text
        for request in session.requests
        if isinstance(request, EditMessageText) and request.text is not None
    ]


async def _feed_command(
    runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    user_id: int,
    text: str,
) -> FakeTelegramSession:
    """Feed one private-chat command through the configured dispatcher."""
    dispatcher, bot, session = runtime
    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=user_id, text=text)),
    )
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (USER_ID, set(), False, False, "/start"),
        (ADMIN_ID, {ADMIN_ID}, True, False, "/start"),
        (SUPERVISOR_ID, set(), True, True, "/start"),
        (USER_ID + 1, set(), False, False, "/start extra arguments"),
    ],
)
async def test_start_routes_users_and_builds_their_command_menu(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], bool, bool, str],
) -> None:
    """Start sends the appropriate help and command menu for each role."""
    user_id, admin_ids, expected_admin, expected_supervisor, command_text = case
    dispatcher, bot, session = dispatcher_runtime
    access_database.admin_ids = admin_ids

    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=user_id, text=command_text)),
    )

    command_names = _sent_command_names(session)
    texts = _sent_texts(session)

    assert len(texts) == 1
    assert "Привет! 👋 Я бот для работы с LLM в формате чата." in texts[0]
    assert "/forget_me — удалить все свои данные" in texts[0]
    assert ("health" in command_names) is expected_admin
    assert ({"ban", "unban"} <= command_names) is expected_admin
    assert ("🩺 Состояние бота:" in texts[0]) is expected_admin
    assert ({"admin", "admins", "admin_add", "admin_remove"} <= command_names) is (
        expected_supervisor
    )
    assert ("🛠 Управление администраторами:" in texts[0]) is expected_supervisor


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_start_falls_back_to_regular_menu_when_database_fails(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """A failed administrator lookup does not prevent the welcome response."""
    dispatcher, bot, session = dispatcher_runtime
    dispatcher.workflow_data["database"] = _FailingAdminDatabase()

    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=USER_ID + 2, text="/start")),
    )

    command_names = _sent_command_names(session)
    texts = _sent_texts(session)

    assert len(texts) == 1
    assert "Привет! 👋 Я бот для работы с LLM в формате чата." in texts[0]
    assert "health" not in command_names
    assert "🩺 Состояние бота:" not in texts[0]
    assert "admin" not in command_names
    assert "🛠 Управление администраторами:" not in texts[0]


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize(
    "case",
    [(OUTSIDER_ID, "/start"), (OUTSIDER_ID + 1, "/unknown 123")],
)
async def test_dispatcher_denies_commands_without_access(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str],
) -> None:
    """Access middleware rejects both known and unknown commands."""
    dispatcher, bot, session = dispatcher_runtime
    user_id, command_text = case
    dispatcher.workflow_data["settings"] = replace(SETTINGS, ALLOW_ALL_USERS=False)

    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=user_id, text=command_text)),
    )

    assert _sent_texts(session) == ["⛔ У тебя нет доступа к этому боту."]
    assert not any(isinstance(request, SetMyCommands) for request in session.requests)


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize(
    "case",
    [
        (USER_ID + 10, "/not_registered"),
        (USER_ID + 11, "/not_registered unexpected arguments"),
    ],
)
async def test_fallback_handles_unknown_commands_through_dispatcher(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str],
) -> None:
    """Unknown slash commands receive the exact fallback response."""
    dispatcher, bot, session = dispatcher_runtime
    user_id, command_text = case

    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=user_id, text=command_text)),
    )

    assert _sent_texts(session) == ["⛔ Доступ запрещён."]
    assert not any(isinstance(request, SetMyCommands) for request in session.requests)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (HISTORY_USER_ID + 10, "/history_clear extra", "clear"),
        (HISTORY_USER_ID + 11, "/forget_me extra", "forget"),
        (HISTORY_USER_ID + 12, "/history extra", "show"),
    ],
)
async def test_history_basic_commands_through_dispatcher(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    """Basic history commands preserve their behavior with extra arguments."""
    user_id, command_text, operation = case
    access_database.history_limits[user_id] = 17

    session = await _feed_command(dispatcher_runtime, user_id, command_text)

    if operation == "clear":
        expected_text = "🧹 История диалога очищена."
        assert access_database.reset_history_calls == [user_id]
    elif operation == "forget":
        expected_text = "🧹 Все твои данные удалены."
        assert access_database.forgotten_user_ids == [user_id]
    else:
        expected_text = (
            f"📚 Твой лимит истории: 17 полных обменов.\n"
            f"Стандартный лимит: {SETTINGS.DEFAULT_HISTORY_EXCHANGES}."
        )

    assert _sent_texts(session) == [expected_text]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (HISTORY_USER_ID + 20, "/history_clear", "reset_history"),
        (HISTORY_USER_ID + 21, "/forget_me", "forget_user"),
        (HISTORY_USER_ID + 22, "/history", "get_history_limit"),
    ],
)
async def test_history_basic_commands_propagate_database_failures(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    """Basic history commands propagate database failures."""
    user_id, command_text, failed_operation = case
    access_database.failed_operation = failed_operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await _feed_command(dispatcher_runtime, user_id, command_text)

    assert _sent_texts(dispatcher_runtime[2]) == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_history_limit_without_arguments_shows_usage(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """History limit without arguments displays command usage."""
    session = await _feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 30,
        "/history_limit",
    )

    assert _sent_texts(session) == [
        (
            "Использование:\n"
            "/history — показать текущий лимит\n"
            "/history_limit 20 — установить свой лимит\n"
            "/history_limit ID 100 — установить лимит другому пользователю "
            "(только администратор)."
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (HISTORY_USER_ID + 31, set(), 12),
        (HISTORY_ADMIN_ID, {HISTORY_ADMIN_ID}, SETTINGS.MAX_HISTORY_EXCHANGES),
        (SUPERVISOR_ID, set(), SETTINGS.MAX_HISTORY_EXCHANGES),
    ],
)
async def test_history_limit_sets_own_limit_for_user_admin_and_supervisor(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], int],
) -> None:
    """Users, administrators and supervisor can set their own limit."""
    user_id, admin_ids, limit = case
    access_database.admin_ids = admin_ids

    session = await _feed_command(
        dispatcher_runtime,
        user_id,
        f"/history_limit {limit}",
    )

    assert _sent_texts(session) == [
        f"✅ Твой лимит истории установлен: {limit} полных обменов."
    ]
    assert access_database.set_history_limit_calls == [(user_id, limit)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (
            HISTORY_USER_ID + 40,
            "invalid",
            "⚠️ Укажи целое число.\nПример: /history_limit 20",
        ),
        (
            HISTORY_USER_ID + 41,
            "0",
            f"⚠️ Допустимый лимит: от 1 до {SETTINGS.DEFAULT_HISTORY_EXCHANGES}.",
        ),
        (
            HISTORY_USER_ID + 42,
            str(SETTINGS.DEFAULT_HISTORY_EXCHANGES + 1),
            f"⚠️ Допустимый лимит: от 1 до {SETTINGS.DEFAULT_HISTORY_EXCHANGES}.",
        ),
    ],
)
async def test_history_limit_rejects_invalid_own_limits(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    """Invalid own limit arguments are rejected with the exact response."""
    user_id, raw_limit, expected_text = case

    session = await _feed_command(
        dispatcher_runtime,
        user_id,
        f"/history_limit {raw_limit}",
    )

    assert _sent_texts(session) == [expected_text]
    assert access_database.set_history_limit_calls == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_history_limit_denies_non_admin_target_changes(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Regular users cannot change another user's history limit."""
    session = await _feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 50,
        f"/history_limit {HISTORY_TARGET_ID} 10",
    )

    assert _sent_texts(session) == [
        "⛔ Назначать лимиты другим пользователям могут только администраторы."
    ]


@pytest.mark.asyncio
async def test_history_limit_allows_admin_to_change_target_limit(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """An administrator can set another user's history limit."""
    user_id = HISTORY_ADMIN_ID + 1
    limit = 25
    access_database.admin_ids = {user_id}

    session = await _feed_command(
        dispatcher_runtime,
        user_id,
        f"/history_limit {HISTORY_TARGET_ID} {limit}",
    )

    assert _sent_texts(session) == [
        (
            f"✅ Для пользователя {HISTORY_TARGET_ID} установлен лимит "
            f"{limit} полных обменов."
        )
    ]
    assert access_database.set_history_limit_calls == [(HISTORY_TARGET_ID, limit)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (
            HISTORY_ADMIN_ID + 2,
            "invalid 10",
            "⚠️ Укажи корректный ID пользователя и целое число лимита.",
        ),
        (
            HISTORY_ADMIN_ID + 3,
            "0 10",
            "⚠️ ID пользователя должен быть положительным.",
        ),
        (
            HISTORY_ADMIN_ID + 4,
            f"{HISTORY_TARGET_ID} invalid",
            "⚠️ Укажи корректный ID пользователя и целое число лимита.",
        ),
        (
            HISTORY_ADMIN_ID + 5,
            f"{HISTORY_TARGET_ID} 0",
            f"⚠️ Допустимый лимит: от 1 до {SETTINGS.MAX_HISTORY_EXCHANGES}.",
        ),
    ],
)
async def test_history_limit_rejects_invalid_target_arguments(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    """Invalid target IDs and limits are rejected."""
    user_id, arguments, expected_text = case
    access_database.admin_ids = {user_id}

    session = await _feed_command(
        dispatcher_runtime,
        user_id,
        f"/history_limit {arguments}",
    )

    assert _sent_texts(session) == [expected_text]
    assert access_database.set_history_limit_calls == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_history_limit_rejects_too_many_arguments(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """History limit rejects commands with more than two arguments."""
    session = await _feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 70,
        "/history_limit 10 20 30",
    )

    assert _sent_texts(session) == [
        (
            "⚠️ Слишком много аргументов.\n"
            "Пример: /history_limit 20 или /history_limit ID 100."
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (HISTORY_USER_ID + 80, "/history_limit 10", "set_history_limit"),
        (HISTORY_USER_ID + 81, "/history_limit", "get_admin_ids"),
    ],
)
async def test_history_limit_propagates_database_failures(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    """History limit commands propagate failures from database operations."""
    user_id, command_text, failed_operation = case
    if failed_operation == "get_admin_ids":
        access_database.fail_admin_lookup_on = 2
    else:
        access_database.failed_operation = failed_operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await _feed_command(dispatcher_runtime, user_id, command_text)

    assert _sent_texts(dispatcher_runtime[2]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (HISTORY_USER_ID + 90, "/history", "show"),
        (HISTORY_USER_ID + 91, "/history_clear", "clear"),
        (HISTORY_USER_ID + 92, "/forget_me", "forget"),
        (HISTORY_USER_ID + 93, "/history_limit 10", "limit"),
    ],
)
async def test_history_commands_are_denied_without_access(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    """Access middleware denies history commands before database mutations."""
    user_id, command_text, operation = case
    dispatcher_runtime[0].workflow_data["settings"] = replace(
        SETTINGS, ALLOW_ALL_USERS=False
    )

    session = await _feed_command(dispatcher_runtime, user_id, command_text)

    assert _sent_texts(session) == ["⛔ У тебя нет доступа к этому боту."]
    assert access_database.reset_history_calls == []
    assert access_database.forgotten_user_ids == []
    assert access_database.set_history_limit_calls == []
    if operation == "show":
        assert access_database.history_limits.get(user_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (PROMPT_USER_ID, None, "📄 Стандартный", "Тестовый системный промпт"),
        (
            PROMPT_USER_ID + 1,
            "Мой персональный промпт",
            "👤 Персональный",
            "Мой персональный промпт",
        ),
    ],
)
async def test_prompt_command_shows_the_effective_prompt(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str | None, str, str],
) -> None:
    """Prompt displays the standard or personal system prompt."""
    user_id, personal_prompt, source, effective_prompt = case
    if personal_prompt is not None:
        access_database.user_prompts[user_id] = personal_prompt

    session = await _feed_command(dispatcher_runtime, user_id, "/prompt extra")

    assert _sent_texts(session) == [
        (
            "Текущий системный промпт\n"
            f"Источник: {source}\n\n"
            f"{effective_prompt}\n\n"
            "Изменить:\n"
            "/prompt_set\n\n"
            "Сбросить персональный промпт:\n"
            "/prompt_reset"
        )
    ]


@pytest.mark.asyncio
async def test_prompt_command_truncates_a_long_effective_prompt(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Prompt display truncates prompts longer than the display limit."""
    access_database.default_system_prompt = "x" * 3501

    session = await _feed_command(
        dispatcher_runtime,
        PROMPT_USER_ID + 2,
        "/prompt",
    )

    displayed_prompt = "x" * 3500 + "\n\n... (промпт сокращён при отображении)"
    assert _sent_texts(session) == [
        (
            "Текущий системный промпт\n"
            "Источник: 📄 Стандартный\n\n"
            f"{displayed_prompt}\n\n"
            "Изменить:\n"
            "/prompt_set\n\n"
            "Сбросить персональный промпт:\n"
            "/prompt_reset"
        )
    ]


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_prompt_set_starts_the_input_flow(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Prompt set asks for a new prompt even when arguments are supplied."""
    session = await _feed_command(
        dispatcher_runtime,
        PROMPT_USER_ID + 3,
        "/prompt_set extra arguments",
    )

    assert _sent_texts(session) == [
        (
            "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
            "Максимальная длина — 4000 символов.\n"
            "Для отмены используй /cancel."
        )
    ]


@pytest.mark.asyncio
async def test_prompt_save_persists_the_new_personal_prompt(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """A valid prompt is stored and the prompt flow messages are deleted."""
    user_id = PROMPT_USER_ID + 4
    await _feed_command(dispatcher_runtime, user_id, "/prompt_set")

    session = await _feed_command(
        dispatcher_runtime,
        user_id,
        "Новый системный промпт",
    )

    assert access_database.user_prompts[user_id] == "Новый системный промпт"
    assert _sent_texts(session) == [
        (
            "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
            "Максимальная длина — 4000 символов.\n"
            "Для отмены используй /cancel."
        ),
        (
            "✅ Персональный системный промпт сохранён.\n\n"
            "Теперь он используется только в твоём чате."
        ),
    ]
    deleted_ids = [
        request.message_id
        for request in session.requests
        if isinstance(request, DeleteMessage)
    ]
    assert deleted_ids == [900, 1]


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize(
    "case",
    [
        (PROMPT_USER_ID + 5, "   ", "Промпт не может быть пустым. Попробуй ещё раз."),
        (
            PROMPT_USER_ID + 6,
            "x" * 4001,
            "Промпт слишком длинный. Максимум 4000 символов.",
        ),
    ],
)
async def test_prompt_save_rejects_invalid_prompt_text(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    """Empty and oversized prompts are rejected without saving."""
    user_id, prompt_text, expected_text = case
    await _feed_command(dispatcher_runtime, user_id, "/prompt_set")

    session = await _feed_command(dispatcher_runtime, user_id, prompt_text)

    assert _sent_texts(session) == [
        (
            "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
            "Максимальная длина — 4000 символов.\n"
            "Для отмены используй /cancel."
        ),
        expected_text,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (
            PROMPT_USER_ID + 7,
            None,
            "ℹ️ У тебя уже используется стандартный системный промпт.",
        ),
        (
            PROMPT_USER_ID + 8,
            "Персональный промпт",
            (
                "🔄 Персональный системный промпт удалён.\n"
                "Теперь используется стандартный промпт."
            ),
        ),
    ],
)
async def test_prompt_reset_handles_personal_and_standard_prompts(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str | None, str],
) -> None:
    """Prompt reset handles users with and without a personal prompt."""
    user_id, personal_prompt, expected_text = case
    if personal_prompt is not None:
        access_database.user_prompts[user_id] = personal_prompt

    session = await _feed_command(
        dispatcher_runtime,
        user_id,
        "/prompt_reset extra",
    )

    assert _sent_texts(session) == [expected_text]
    assert user_id not in access_database.user_prompts


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_prompt_cancel_clears_the_input_flow(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Cancel ends the prompt input flow and sends its status."""
    user_id = PROMPT_USER_ID + 9
    await _feed_command(dispatcher_runtime, user_id, "/prompt_set")

    session = await _feed_command(dispatcher_runtime, user_id, "/cancel extra")

    assert _sent_texts(session) == [
        (
            "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
            "Максимальная длина — 4000 символов.\n"
            "Для отмены используй /cancel."
        ),
        "❎ Ввод системного промпта отменён.",
    ]
    deleted_ids = [
        request.message_id
        for request in session.requests
        if isinstance(request, DeleteMessage)
    ]
    assert deleted_ids == [900, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failed_operation",
    ["get_user_system_prompt", "get_system_prompt"],
)
async def test_prompt_view_propagates_database_failures(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    failed_operation: str,
) -> None:
    """Prompt view propagates failures from either prompt lookup."""
    access_database.failed_operation = failed_operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await _feed_command(
            dispatcher_runtime,
            PROMPT_USER_ID + 10,
            "/prompt",
        )

    assert _sent_texts(dispatcher_runtime[2]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        ("get_user_system_prompt", False),
        ("delete_system_prompt", True),
    ],
)
async def test_prompt_reset_propagates_database_failures(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[str, bool],
) -> None:
    """Prompt reset propagates lookup and deletion failures."""
    failed_operation, has_personal_prompt = case
    user_id = PROMPT_USER_ID + 11
    if has_personal_prompt:
        access_database.user_prompts[user_id] = "Personal prompt"
    access_database.failed_operation = failed_operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await _feed_command(
            dispatcher_runtime,
            user_id,
            "/prompt_reset",
        )

    assert _sent_texts(dispatcher_runtime[2]) == []


@pytest.mark.asyncio
async def test_prompt_save_propagates_database_failure(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Saving a personal prompt propagates a database failure."""
    user_id = PROMPT_USER_ID + 12
    session = await _feed_command(dispatcher_runtime, user_id, "/prompt_set")
    access_database.failed_operation = "set_system_prompt"

    with pytest.raises(RuntimeError, match="database unavailable"):
        await _feed_command(
            dispatcher_runtime,
            user_id,
            "New prompt",
        )

    assert _sent_texts(session) == [
        (
            "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
            "Максимальная длина — 4000 символов.\n"
            "Для отмены используй /cancel."
        )
    ]


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize(
    "case",
    [
        (PROMPT_USER_ID + 20, "/prompt"),
        (PROMPT_USER_ID + 21, "/prompt_set"),
        (PROMPT_USER_ID + 22, "/prompt_reset"),
    ],
)
async def test_prompt_commands_are_denied_without_access(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str],
) -> None:
    """Access middleware denies prompt commands before handler execution."""
    user_id, command_text = case
    dispatcher_runtime[0].workflow_data["settings"] = replace(
        SETTINGS, ALLOW_ALL_USERS=False
    )

    session = await _feed_command(dispatcher_runtime, user_id, command_text)

    assert _sent_texts(session) == ["⛔ У тебя нет доступа к этому боту."]


@pytest.mark.asyncio
async def test_health_reports_all_component_statuses(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Health reports Telegram, database and LLM status."""
    access_database.admin_ids = {HISTORY_ADMIN_ID}

    session = await _feed_command(dispatcher_runtime, HISTORY_ADMIN_ID, "/health extra")

    assert _sent_texts(session) == ["🔎 Проверяю состояние компонентов..."]
    assert _edited_texts(session) == [
        (
            "🩺 <b>Состояние бота</b>\n\n"
            "🟢 Telegram API: Доступен\n"
            "🟢 База данных: Подключена\n"
            "🟢 Инференс: Доступен"
        )
    ]


@pytest.mark.asyncio
async def test_health_reports_failed_telegram_database_and_llm(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health reports failed dependencies without aborting the command."""

    async def fail_get_me(_bot: Bot) -> User:
        msg = "Telegram unavailable"
        raise RuntimeError(msg)

    dispatcher, bot, session = dispatcher_runtime
    access_database.failed_operation = "health_check"
    monkeypatch.setattr(Bot, "get_me", fail_get_me)
    dispatcher.workflow_data["llm_client"] = _FakeLLM((False, "Недоступен"))

    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=SUPERVISOR_ID, text="/health")),
    )

    assert _sent_texts(session) == ["🔎 Проверяю состояние компонентов..."]
    assert _edited_texts(session) == [
        (
            "🩺 <b>Состояние бота</b>\n\n"
            "🔴 Telegram API: Недоступен\n"
            "🔴 База данных: Ошибка подключения\n"
            "🔴 Инференс: Недоступен"
        )
    ]


@pytest.mark.asyncio
async def test_health_denies_user_when_admin_lookup_fails(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Health reports a permission lookup failure to a non-supervisor."""
    access_database.fail_admin_lookup_on = 2

    session = await _feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 100,
        "/health",
    )

    assert _sent_texts(session) == ["⚠️ Не удалось проверить права администратора."]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_text",
    ["/admin", "/admins", "/admin_add 123", "/admin_remove 123"],
)
async def test_supervisor_commands_deny_non_supervisor(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    command_text: str,
) -> None:
    """Supervisor-only commands reject ordinary users."""
    session = await _feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 101,
        command_text,
    )

    assert _sent_texts(session) == ["⛔ Доступ запрещён."]
    assert access_database.add_admin_calls == []
    assert access_database.remove_admin_calls == []


@pytest.mark.asyncio
async def test_admin_panel_reports_database_counts(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Admin panel displays administrator and allowlist counts."""
    access_database.admin_ids = {8003, 8001, 8002}

    session = await _feed_command(dispatcher_runtime, SUPERVISOR_ID, "/admin extra")

    assert _sent_texts(session) == [
        (
            "🛠 Панель управления\n\n"
            f"👑 Supervisor ID: {SUPERVISOR_ID}\n"
            "👥 Обычных администраторов: 3\n"
            "🔐 Пользователей в allowlist: 0\n\n"
            "Команды управления:\n"
            "/admins — список администраторов\n"
            "/admin_add ID — добавить администратора\n"
            "/admin_remove ID — удалить администратора"
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("admin_ids", "expected_text"),
    [
        (
            {8003, 8001, 8002},
            (
                f"👥 Список администраторов\n\n👑 Supervisor: {SUPERVISOR_ID}\n"
                "\nОбычные администраторы:\n• 8001\n• 8002\n• 8003"
            ),
        ),
        (
            set(),
            (
                f"👥 Список администраторов\n\n👑 Supervisor: {SUPERVISOR_ID}\n"
                "\nОбычных администраторов пока нет."
            ),
        ),
    ],
)
async def test_admins_lists_sorted_ids_or_empty_state(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    admin_ids: set[int],
    expected_text: str,
) -> None:
    """Admins lists sorted IDs and handles an empty administrator list."""
    access_database.admin_ids = admin_ids

    session = await _feed_command(dispatcher_runtime, SUPERVISOR_ID, "/admins")

    assert _sent_texts(session) == [expected_text]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command_text", "operation"),
    [("/admin", "get_admin_ids"), ("/admins", "get_admin_ids")],
)
async def test_admin_read_commands_propagate_database_failures(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    command_text: str,
    operation: str,
) -> None:
    """Admin panel and list propagate database lookup failures."""
    access_database.failed_operation = operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await _feed_command(dispatcher_runtime, SUPERVISOR_ID, command_text)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (True, "✅ Пользователь 8001 добавлен в список администраторов."),
        (False, "ℹ️ Пользователь 8001 уже является администратором."),
    ],
)
async def test_admin_add_reports_added_and_existing_users(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[bool, str],
) -> None:
    """Admin add reports both newly added and existing administrators."""
    result, expected_text = case
    access_database.add_admin_result = result

    session = await _feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        "/admin_add 8001",
    )

    assert _sent_texts(session) == [expected_text]
    assert access_database.add_admin_calls == [8001]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "expected_text"),
    [
        ("", "Укажи Telegram ID пользователя.\nПример: /admin_add 123456789"),
        ("invalid", "⛔ Telegram ID должен быть целым числом."),
        ("0", "⛔ Telegram ID должен быть положительным числом."),
        (
            str(SUPERVISOR_ID),
            "ℹ️ Этот пользователь уже является Supervisor.",
        ),
    ],
)
async def test_admin_add_rejects_invalid_arguments_and_supervisor(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
    expected_text: str,
) -> None:
    """Admin add validates IDs and protects the supervisor."""
    session = await _feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/admin_add {arguments}".rstrip(),
    )

    assert _sent_texts(session) == [expected_text]
    assert access_database.add_admin_calls == []


@pytest.mark.asyncio
async def test_admin_add_propagates_database_failure(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Admin add propagates database failures."""
    access_database.failed_operation = "add_admin"

    with pytest.raises(RuntimeError, match="database unavailable"):
        await _feed_command(dispatcher_runtime, SUPERVISOR_ID, "/admin_add 8001")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (True, "✅ Пользователь 8001 удалён из списка администраторов."),
        (False, "ℹ️ Пользователь 8001 не найден среди администраторов."),
    ],
)
async def test_admin_remove_reports_removed_and_missing_users(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[bool, str],
) -> None:
    """Admin remove reports successful and unsuccessful removals."""
    result, expected_text = case
    access_database.remove_admin_result = result

    session = await _feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        "/admin_remove 8001",
    )

    assert _sent_texts(session) == [expected_text]
    assert access_database.remove_admin_calls == [8001]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "expected_text"),
    [
        ("", "Укажи Telegram ID пользователя.\nПример: /admin_remove 123456789"),
        ("invalid", "⛔ Telegram ID должен быть целым числом."),
        ("0", "⛔ Telegram ID должен быть положительным числом."),
        (str(SUPERVISOR_ID), "⛔ Нельзя удалить Supervisor."),
    ],
)
async def test_admin_remove_rejects_invalid_arguments_and_supervisor(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
    expected_text: str,
) -> None:
    """Admin remove validates IDs and protects the supervisor."""
    session = await _feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/admin_remove {arguments}".rstrip(),
    )

    assert _sent_texts(session) == [expected_text]
    assert access_database.remove_admin_calls == []


@pytest.mark.asyncio
async def test_admin_remove_propagates_database_failure(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Admin remove propagates database failures."""
    access_database.failed_operation = "remove_admin"

    with pytest.raises(RuntimeError, match="database unavailable"):
        await _feed_command(dispatcher_runtime, SUPERVISOR_ID, "/admin_remove 8001")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (True, "✅ Пользователь 8001 заблокирован."),
        (False, "ℹ️ Пользователь 8001 уже заблокирован."),
    ],
)
async def test_ban_reports_blocked_and_already_blocked_users(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[bool, str],
) -> None:
    """Ban reports both new and existing blocks."""
    result, expected_text = case
    access_database.block_user_result = result

    session = await _feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        "/ban 8001",
    )

    assert _sent_texts(session) == [expected_text]
    assert access_database.block_user_calls == [8001]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    ["", "invalid", "0", "-1"],
)
async def test_ban_rejects_invalid_target_ids(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
) -> None:
    """Ban requires a positive integer Telegram ID."""
    session = await _feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/ban {arguments}".rstrip(),
    )

    assert _sent_texts(session) == [
        "Укажи положительный Telegram ID. Пример: /ban 123456789"
    ]
    assert access_database.block_user_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("target_id", [SUPERVISOR_ID, 8002])
async def test_ban_protects_supervisor_and_administrators(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    target_id: int,
) -> None:
    """Ban refuses to block the supervisor or another administrator."""
    access_database.admin_ids = {8002}

    session = await _feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/ban {target_id}",
    )

    assert _sent_texts(session) == [
        (
            "⛔ Этого пользователя заблокировать нельзя. "
            "Сначала сними права администратора."
        )
    ]
    assert access_database.block_user_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_operation", ["get_admin_ids", "block_user"])
async def test_ban_propagates_database_failures(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    failed_operation: str,
) -> None:
    """Ban propagates permission lookup and block operation failures."""
    access_database.failed_operation = failed_operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await _feed_command(dispatcher_runtime, SUPERVISOR_ID, "/ban 8001")


@pytest.mark.asyncio
async def test_unban_reports_success_and_missing_blocks(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Unban reports successful and unsuccessful unblock operations."""
    session = await _feed_command(dispatcher_runtime, SUPERVISOR_ID, "/unban 8001")
    assert _sent_texts(session) == ["✅ Блокировка пользователя 8001 снята."]

    access_database.unblock_user_result = False
    session = await _feed_command(dispatcher_runtime, SUPERVISOR_ID, "/unban 8002")
    assert _sent_texts(session)[-1:] == ["ℹ️ Пользователь 8002 не был заблокирован."]
    assert access_database.unblock_user_calls == [8001, 8002]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    ["", "invalid", "0", "-1"],
)
async def test_unban_rejects_invalid_target_ids(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
) -> None:
    """Unban requires a positive integer Telegram ID."""
    session = await _feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/unban {arguments}".rstrip(),
    )

    assert _sent_texts(session) == [
        "Укажи положительный Telegram ID. Пример: /unban 123456789"
    ]
    assert access_database.unblock_user_calls == []


@pytest.mark.asyncio
async def test_unban_propagates_database_failure(
    access_database: _AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Unban propagates database failures."""
    access_database.failed_operation = "unblock_user"

    with pytest.raises(RuntimeError, match="database unavailable"):
        await _feed_command(dispatcher_runtime, SUPERVISOR_ID, "/unban 8001")
