# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Shared helpers for dispatcher tests."""

from aiogram import Bot, Dispatcher, Router
from aiogram.methods import (
    SendMessage,
)

from bot_obormot.middlewares.throttle import ThrottleMiddleware
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


class AccessDatabase:
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


class FakeLLM:
    """Provide an offline LLM health-check response."""

    def __init__(self, result: tuple[bool, str] = (True, "Доступен")) -> None:
        self.result = result

    async def health_check(self) -> tuple[bool, str]:
        """Return the configured LLM health status."""
        return self.result


def reset_throttle(dispatcher: Dispatcher) -> None:
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
