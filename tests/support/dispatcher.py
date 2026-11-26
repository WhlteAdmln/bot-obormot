# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Shared helpers for dispatcher tests."""

from collections.abc import Callable
from dataclasses import dataclass, field

from aiogram import Bot, Dispatcher
from aiogram.methods import (
    SendMessage,
)

from tests.support.settings import make_settings
from tests.support.telegram import (
    FakeTelegramSession,
    make_message,
    make_update,
)

SUPERVISOR_ID = 999999999


ADMIN_ID = 111111111


USER_ID = 222222222


HISTORY_USER_ID = 444000000


HISTORY_ADMIN_ID = 444000001


SETTINGS = make_settings(SUPERVISOR_ID=SUPERVISOR_ID, ALLOW_ALL_USERS=True)


@dataclass
class DatabaseScenario:
    """Describe how the fake database misbehaves in one test."""

    failed_operation: str | None = None
    fail_admin_lookup_on: int | None = None
    results: dict[str, bool] = field(default_factory=dict)

    def check(self, operation: str) -> None:
        """Raise when the scenario makes this operation fail."""
        if self.failed_operation == operation:
            msg = "database unavailable"
            raise RuntimeError(msg)

    def result_of(self, operation: str) -> bool:
        """Return the outcome of a change operation, successful by default."""
        return self.results.get(operation, True)


@dataclass
class CallLog:
    """Record the database operations a handler performed."""

    calls: list[tuple[str, tuple[int, ...]]] = field(default_factory=list)

    def record(self, operation: str, *arguments: int) -> None:
        """Remember one call with its arguments."""
        self.calls.append((operation, arguments))

    def arguments(self, operation: str) -> list[tuple[int, ...]]:
        """Return the arguments of every call to one operation."""
        return [arguments for name, arguments in self.calls if name == operation]

    def count(self, operation: str) -> int:
        """Return how many times an operation was called."""
        return len(self.arguments(operation))


class AccessDatabase:
    """Provide deterministic database responses for dispatcher tests."""

    def __init__(self, admin_ids: set[int] | None = None) -> None:
        """Start with the given admins and an empty database state."""
        self.admin_ids = set(admin_ids or ())
        self.blocked_user_ids: set[int] = set()
        self.history_limits: dict[int, int] = {}
        self.user_prompts: dict[int, str] = {}
        self.default_system_prompt = "Тестовый системный промпт"
        self.scenario = DatabaseScenario()
        self.log = CallLog()

    async def get_blocked_ids(self) -> set[int]:
        """Return configured blocked users."""
        self.scenario.check("get_blocked_ids")
        return self.blocked_user_ids

    async def get_admin_ids(self) -> set[int]:
        """Return configured administrator IDs."""
        self.log.record("get_admin_ids")
        if self.log.count("get_admin_ids") == self.scenario.fail_admin_lookup_on:
            msg = "database unavailable"
            raise RuntimeError(msg)
        self.scenario.check("get_admin_ids")
        return self.admin_ids

    async def reset_history(self, user_id: int) -> None:
        """Record a dialog history reset."""
        self.scenario.check("reset_history")
        self.log.record("reset_history", user_id)

    async def forget_user(self, user_id: int) -> None:
        """Record a complete user data deletion."""
        self.scenario.check("forget_user")
        self.log.record("forget_user", user_id)

    async def get_history_limit(self, user_id: int) -> int:
        """Return the configured history limit or a test default."""
        self.scenario.check("get_history_limit")
        return self.history_limits.get(user_id, 17)

    async def set_history_limit(self, user_id: int, limit: int) -> None:
        """Record and store a history limit."""
        self.scenario.check("set_history_limit")
        self.history_limits[user_id] = limit
        self.log.record("set_history_limit", user_id, limit)

    async def get_user_system_prompt(self, user_id: int) -> str | None:
        """Return a user's personal system prompt."""
        self.scenario.check("get_user_system_prompt")
        return self.user_prompts.get(user_id)

    async def get_system_prompt(self, user_id: int) -> str:
        """Return the effective system prompt."""
        self.scenario.check("get_system_prompt")
        return self.user_prompts.get(user_id, self.default_system_prompt)

    async def set_system_prompt(self, user_id: int, prompt: str) -> None:
        """Store a user's personal system prompt."""
        self.scenario.check("set_system_prompt")
        self.user_prompts[user_id] = prompt

    async def delete_system_prompt(self, user_id: int) -> None:
        """Remove a user's personal system prompt."""
        self.scenario.check("delete_system_prompt")
        self.user_prompts.pop(user_id, None)

    async def health_check(self) -> bool:
        """Return a successful database health check."""
        self.scenario.check("health_check")
        return True

    async def add_admin(self, user_id: int) -> bool:
        """Record an administrator addition."""
        return self._change("add_admin", user_id, self.admin_ids.add)

    async def remove_admin(self, user_id: int) -> bool:
        """Record an administrator removal."""
        return self._change("remove_admin", user_id, self.admin_ids.discard)

    async def block_user(self, user_id: int) -> bool:
        """Record a user block."""
        return self._change("block_user", user_id, self.blocked_user_ids.add)

    async def unblock_user(self, user_id: int) -> bool:
        """Record a user unblock."""
        return self._change("unblock_user", user_id, self.blocked_user_ids.discard)

    def _change(
        self,
        operation: str,
        user_id: int,
        apply: Callable[[int], None],
    ) -> bool:
        self.scenario.check(operation)
        self.log.record(operation, user_id)
        result = self.scenario.result_of(operation)
        if result:
            apply(user_id)
        return result


class FakeLLM:
    """Provide an offline LLM health-check response."""

    def __init__(self, result: tuple[bool, str] = (True, "Доступен")) -> None:
        """Store the health-check result to return."""
        self.result = result

    async def health_check(self) -> tuple[bool, str]:
        """Return the configured LLM health status."""
        return self.result


def sent_texts(session: FakeTelegramSession) -> list[str]:
    """Extract text fields from outgoing SendMessage requests."""
    return [
        request.text for request in session.requests if isinstance(request, SendMessage)
    ]


async def feed_command(
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
