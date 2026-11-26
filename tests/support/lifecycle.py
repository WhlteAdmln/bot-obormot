# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Recording fakes for application composition and lifecycle tests."""

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace, TracebackType
from typing import Self

from bot_obormot.settings import Settings


class FakeRouterDispatcher:
    """Record middleware and routers attached by the router configuration."""

    def __init__(self) -> None:
        """Start with no middleware, routers, startup callbacks or workflow data."""
        self.middleware_calls: list[object] = []
        self.routers: list[object] = []
        self.workflow_data: dict[str, object] = {}
        self.message = SimpleNamespace(middleware=self.middleware_calls.append)
        self.startup_callbacks: list[object] = []
        self.startup = SimpleNamespace(register=self.startup_callbacks.append)

    def include_router(self, router: object) -> None:
        """Record an included router."""
        self.routers.append(router)


def make_lifecycle_bot(calls: list[str]) -> SimpleNamespace:
    """Make a bot whose session records closing."""

    async def close_session() -> None:
        calls.append("telegram.close")

    return SimpleNamespace(session=SimpleNamespace(close=close_session))


class FakeLifecycleDispatcher:
    """Record polling and the arguments it was started with."""

    def __init__(self, calls: list[str]) -> None:
        """Share the call log with the other lifecycle fakes."""
        self.calls = calls
        self.polling_arguments: list[tuple[object, dict[str, object]]] = []

    async def start_polling(self, bot: object, **kwargs: object) -> None:
        """Record polling and let pending background tasks start."""
        self.polling_arguments.append((bot, kwargs))
        self.calls.append("polling")
        await asyncio.sleep(0)


class FakeManagedDatabase:
    """Record entering and leaving the database context."""

    def __init__(self, calls: list[str]) -> None:
        """Share the call log; entering succeeds until ``fail_on_enter`` is set."""
        self.calls = calls
        self.fail_on_enter = False

    async def __aenter__(self) -> Self:
        """Record the connection or raise the configured failure."""
        self.calls.append("database.connect")
        if self.fail_on_enter:
            msg = "application database unavailable"
            raise RuntimeError(msg)
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Record closing the connection."""
        self.calls.append("database.close")


class FakeLifecycleLLM:
    """Record configuration, startup and closing of the LLM client."""

    def __init__(self, calls: list[object]) -> None:
        """Share the call log with the other lifecycle fakes."""
        self.calls = calls
        self.settings: Settings | None = None

    def configure(self, settings: Settings) -> None:
        """Record the configured settings."""
        self.settings = settings
        self.calls.append("llm.configure")

    async def start(self) -> None:
        """Record startup."""
        self.calls.append("llm.start")

    async def close(self) -> None:
        """Record closing."""
        self.calls.append("llm.close")


@dataclass
class LifecycleHarness:
    """Group the lifecycle fakes around one shared call log."""

    calls: list[str] = field(default_factory=list)
    database: FakeManagedDatabase = field(init=False)
    llm: FakeLifecycleLLM = field(init=False)
    bot: SimpleNamespace = field(init=False)
    dispatcher: FakeLifecycleDispatcher = field(init=False)

    def __post_init__(self) -> None:
        """Create every fake with the shared call log."""
        self.database = FakeManagedDatabase(self.calls)
        self.llm = FakeLifecycleLLM(self.calls)
        self.bot = make_lifecycle_bot(self.calls)
        self.dispatcher = FakeLifecycleDispatcher(self.calls)
