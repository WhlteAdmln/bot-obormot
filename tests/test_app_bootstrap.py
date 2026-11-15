# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for application composition and resource lifecycle."""

import asyncio
import importlib
import logging
import sys
import types
from collections.abc import Iterator
from types import SimpleNamespace

import pytest


def _module(name: str, **attributes: object) -> types.ModuleType:
    result = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(result, key, value)
    return result


@pytest.fixture
def router_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[object, ...]]:
    """Router dependencies."""

    class FakeDispatcher:
        def __init__(self) -> None:
            self.middleware_calls = []
            self.routers = []
            self.message = SimpleNamespace(middleware=self.middleware_calls.append)

        def include_router(self, router: object) -> None:
            self.routers.append(router)

    class FakeAccessMiddleware:
        pass

    class FakeThrottleMiddleware:
        pass

    class FakeCleanupMiddleware:
        pass

    router_refs = {name: object() for name in ("start", "admin", "commands", "chat")}
    handlers_package = _module(
        "bot.handlers",
        **{
            name: SimpleNamespace(router=router) for name, router in router_refs.items()
        },
    )
    middlewares_package = _module("bot.middlewares")

    monkeypatch.setitem(
        sys.modules,
        "aiogram",
        _module("aiogram", Dispatcher=FakeDispatcher),
    )
    monkeypatch.setitem(sys.modules, "bot.handlers", handlers_package)
    monkeypatch.setitem(
        sys.modules,
        "bot.middlewares.throttle",
        _module("bot.middlewares.throttle", ThrottleMiddleware=FakeThrottleMiddleware),
    )
    monkeypatch.setitem(
        sys.modules,
        "bot.middlewares.access",
        _module("bot.middlewares.access", AccessMiddleware=FakeAccessMiddleware),
    )
    monkeypatch.setitem(
        sys.modules,
        "bot.middlewares.temporary_messages",
        _module(
            "bot.middlewares.temporary_messages",
            TemporaryMessagesCleanupMiddleware=FakeCleanupMiddleware,
        ),
    )
    monkeypatch.setitem(sys.modules, "bot.middlewares", middlewares_package)

    sys.modules.pop("bot.app.routers", None)
    routers_module = importlib.import_module("bot.app.routers")
    yield (
        FakeDispatcher,
        FakeThrottleMiddleware,
        FakeAccessMiddleware,
        FakeCleanupMiddleware,
        router_refs,
        routers_module,
    )
    sys.modules.pop("bot.app.routers", None)


def test_dispatcher_registers_middlewares_and_routers_once_in_original_order(
    router_dependencies: tuple[object, ...],
) -> None:
    """Dispatcher registers middlewares and routers once in original order."""
    (
        fake_dispatcher,
        fake_throttle_middleware,
        fake_access_middleware,
        fake_cleanup_middleware,
        router_refs,
        routers_module,
    ) = router_dependencies

    dispatcher = fake_dispatcher()
    configured = routers_module.configure_dispatcher(dispatcher)

    assert configured is dispatcher
    assert len(dispatcher.middleware_calls) == 3
    assert isinstance(dispatcher.middleware_calls[0], fake_throttle_middleware)
    assert isinstance(dispatcher.middleware_calls[1], fake_access_middleware)
    assert isinstance(dispatcher.middleware_calls[2], fake_cleanup_middleware)
    assert len(dispatcher.routers) == 4
    assert dispatcher.routers == [
        router_refs["start"],
        router_refs["admin"],
        router_refs["commands"],
        router_refs["chat"],
    ]


def test_periodic_cleanup_uses_existing_policy_and_propagates_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Periodic cleanup uses existing policy and propagates cancellation."""
    calls = []

    class FakeDatabase:
        async def cleanup_old_images(self, **kwargs: object) -> dict[str, object]:
            calls.append(kwargs)
            return {"old_images": 1, "orphan_images": 2, "failed": 0}

    async def stop_after_first_iteration(_delay: object) -> None:
        raise asyncio.CancelledError

    monkeypatch.setitem(
        sys.modules,
        "bot.services.database",
        _module("bot.services.database", db=FakeDatabase()),
    )
    sys.modules.pop("bot.app.background.image_cleanup", None)
    image_cleanup = importlib.import_module("bot.app.background.image_cleanup")

    monkeypatch.setattr(image_cleanup, "db", FakeDatabase())
    monkeypatch.setattr(image_cleanup.asyncio, "sleep", stop_after_first_iteration)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(image_cleanup.periodic_image_cleanup())

    assert calls == [{"retention_days": 30, "orphan_grace_hours": 24}]
    assert image_cleanup.IMAGE_CLEANUP_INTERVAL == 24 * 60 * 60


@pytest.fixture
def lifecycle_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[object, ...]]:
    """Lifecycle dependencies."""
    calls = []

    class FakeBot:
        def __init__(self) -> None:
            async def close_session() -> None:
                calls.append("telegram.close")

            self.session = SimpleNamespace(close=close_session)

    class FakeDispatcher:
        async def start_polling(self, bot: object, **kwargs: object) -> None:
            assert isinstance(bot, FakeBot)
            assert kwargs == {"close_bot_session": False}
            calls.append("polling")
            # Let the just-created background task start before polling returns.
            await asyncio.sleep(0)

    class FakeDatabase:
        async def connect(self) -> None:
            calls.append("db.connect")

        async def close(self) -> None:
            calls.append("db.close")

    class FakeLLM:
        async def start(self) -> None:
            calls.append("llm.start")

        async def close(self) -> None:
            calls.append("llm.close")

    async def fake_periodic_cleanup() -> None:
        calls.append("cleanup.start")
        try:
            await asyncio.Future()
        finally:
            calls.append("cleanup.stop")

    monkeypatch.setitem(
        sys.modules,
        "aiogram",
        _module(
            "aiogram",
            Bot=FakeBot,
            Dispatcher=FakeDispatcher,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "bot.services.database",
        _module("bot.services.database", db=FakeDatabase()),
    )
    monkeypatch.setitem(
        sys.modules,
        "bot.services.llm",
        _module("bot.services.llm", llm_client=FakeLLM()),
    )
    monkeypatch.setitem(
        sys.modules,
        "bot.app.background.image_cleanup",
        _module(
            "bot.app.background.image_cleanup",
            IMAGE_CLEANUP_INTERVAL=86400,
            periodic_image_cleanup=fake_periodic_cleanup,
        ),
    )
    sys.modules.pop("bot.app.lifecycle", None)
    lifecycle = importlib.import_module("bot.app.lifecycle")

    yield FakeBot, FakeDispatcher, calls, lifecycle
    sys.modules.pop("bot.app.lifecycle", None)


def _async_call(calls: object, value: object) -> None:
    calls.append(value)


def test_lifecycle_preserves_startup_polling_and_shutdown_order(
    lifecycle_dependencies: tuple[object, ...],
) -> None:
    """Lifecycle preserves startup polling and shutdown order."""
    fake_bot, fake_dispatcher, calls, lifecycle = lifecycle_dependencies

    asyncio.run(lifecycle.run_application(fake_bot(), fake_dispatcher()))

    assert calls == [
        "db.connect",
        "llm.start",
        "polling",
        "cleanup.start",
        "cleanup.stop",
        "llm.close",
        "db.close",
        "telegram.close",
    ]


def test_lifecycle_closes_remaining_resources_when_startup_fails(
    lifecycle_dependencies: tuple[object, ...],
) -> None:
    """Lifecycle closes remaining resources when startup fails."""
    fake_bot, fake_dispatcher, calls, lifecycle = lifecycle_dependencies

    async def fail_connect() -> None:
        calls.append("db.connect")
        msg = "database unavailable"
        raise RuntimeError(msg)

    lifecycle.db.connect = fail_connect

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(lifecycle.run_application(fake_bot(), fake_dispatcher()))

    assert calls == [
        "db.connect",
        "llm.close",
        "db.close",
        "telegram.close",
    ]


def test_lifecycle_continues_closing_after_one_cleanup_error(
    lifecycle_dependencies: tuple[object, ...],
) -> None:
    """Lifecycle continues closing after one cleanup error."""
    fake_bot, fake_dispatcher, calls, lifecycle = lifecycle_dependencies

    async def fail_llm_close() -> None:
        calls.append("llm.close")
        msg = "LLM close failed"
        raise RuntimeError(msg)

    lifecycle.llm_client.close = fail_llm_close

    asyncio.run(lifecycle.run_application(fake_bot(), fake_dispatcher()))

    assert calls[-3:] == ["llm.close", "db.close", "telegram.close"]


def test_bootstrap_main_calls_components_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap main calls components in order."""
    calls = []
    bot_instance = object()
    dispatcher_instance = object()

    monkeypatch.setitem(
        sys.modules,
        "aiogram",
        _module("aiogram", Bot=object, Dispatcher=object),
    )

    async def run_application(bot: object, dispatcher: object) -> None:
        assert bot is bot_instance
        assert dispatcher is dispatcher_instance
        calls.append("run")

    monkeypatch.setitem(
        sys.modules,
        "bot.app.lifecycle",
        _module("bot.app.lifecycle", run_application=run_application),
    )
    monkeypatch.setitem(
        sys.modules,
        "bot.app.routers",
        _module(
            "bot.app.routers",
            configure_dispatcher=lambda dispatcher: dispatcher,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "bot.app.logging_setup",
        _module(
            "bot.app.logging_setup",
            configure_logging=lambda: calls.append("logging"),
        ),
    )
    media_package = _module("bot.services.media")
    media_package.__path__ = []
    monkeypatch.setitem(sys.modules, "bot.services.media", media_package)
    monkeypatch.setitem(
        sys.modules,
        "bot.services.media.safety",
        _module(
            "bot.services.media.safety",
            configure_pillow_limits=lambda: calls.append("pillow_limits"),
        ),
    )
    sys.modules.pop("bot.app.bootstrap", None)
    bootstrap = importlib.import_module("bot.app.bootstrap")

    monkeypatch.setattr(
        bootstrap.os, "umask", lambda mask: calls.append(("umask", mask))
    )
    monkeypatch.setattr(bootstrap, "configure_logging", lambda: calls.append("logging"))
    monkeypatch.setattr(
        bootstrap, "log_access_mode", lambda: calls.append("access_mode")
    )
    monkeypatch.setattr(
        bootstrap, "create_bot", lambda: (calls.append("bot"), bot_instance)[1]
    )
    monkeypatch.setattr(
        bootstrap,
        "create_dispatcher",
        lambda: (calls.append("dispatcher"), dispatcher_instance)[1],
    )

    monkeypatch.setattr(bootstrap, "run_application", run_application)
    asyncio.run(bootstrap.main())

    assert calls == [
        ("umask", 0o077),
        "logging",
        "pillow_limits",
        "access_mode",
        "bot",
        "dispatcher",
        "run",
    ]


def test_main_module_is_a_thin_compatible_entrypoint() -> None:
    """Main module is a thin compatible entrypoint."""
    main_module = importlib.import_module("bot.main")
    image_cleanup = importlib.import_module("bot.app.background.image_cleanup")
    bootstrap = importlib.import_module("bot.app.bootstrap")

    assert main_module.main is bootstrap.main
    assert main_module.periodic_image_cleanup is image_cleanup.periodic_image_cleanup
    assert main_module.IMAGE_CLEANUP_INTERVAL == image_cleanup.IMAGE_CLEANUP_INTERVAL


@pytest.mark.parametrize(
    ("allow_all", "allowed_users", "expected_message", "expected_level"),
    [
        (
            True,
            {10},
            "ACCESS MODE: open to everyone (ALLOW_ALL_USERS=true)",
            "WARNING",
        ),
        (False, {10, 20}, "ACCESS MODE: allowlist, 2 users", "INFO"),
        (
            False,
            set(),
            "ACCESS MODE: only supervisor and administrators (ALLOWED_USERS is empty)",
            "WARNING",
        ),
    ],
)
def test_log_access_mode_reports_configured_mode(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    allow_all: object,
    allowed_users: object,
    expected_message: str,
    expected_level: str,
) -> None:
    """Log access mode reports configured mode."""
    bootstrap = importlib.import_module("bot.app.bootstrap")
    config = importlib.import_module("bot.config").config

    monkeypatch.setattr(config, "ALLOW_ALL_USERS", allow_all)
    monkeypatch.setattr(config, "ALLOWED_USERS", allowed_users)

    with caplog.at_level(logging.DEBUG, logger="bot.main"):
        bootstrap.log_access_mode()

    assert any(
        record.levelname == expected_level and expected_message in record.message
        for record in caplog.records
    )


@pytest.fixture
def bootstrap_module(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[object, ...]]:
    """Bootstrap module."""
    created_tokens = []

    class FakeBot:
        def __init__(self, token: str) -> None:
            self.token = token
            created_tokens.append(token)

    monkeypatch.setitem(
        sys.modules,
        "aiogram",
        _module("aiogram", Bot=FakeBot, Dispatcher=object),
    )
    monkeypatch.setitem(
        sys.modules,
        "bot.app.lifecycle",
        _module("bot.app.lifecycle", run_application=None),
    )
    monkeypatch.setitem(
        sys.modules,
        "bot.app.logging_setup",
        _module("bot.app.logging_setup", configure_logging=None),
    )
    monkeypatch.setitem(
        sys.modules,
        "bot.app.routers",
        _module("bot.app.routers", configure_dispatcher=None),
    )
    media_package = _module("bot.services.media")
    media_package.__path__ = []
    monkeypatch.setitem(sys.modules, "bot.services.media", media_package)
    monkeypatch.setitem(
        sys.modules,
        "bot.services.media.safety",
        _module("bot.services.media.safety", configure_pillow_limits=None),
    )

    sys.modules.pop("bot.app.bootstrap", None)
    bootstrap = importlib.import_module("bot.app.bootstrap")
    yield bootstrap, created_tokens
    sys.modules.pop("bot.app.bootstrap", None)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "YOUR_TELEGRAM_BOT_TOKEN",
        "abc",
        "123456789:SHORT",
        "12345:contains spaces and punctuation!",
        "123456789:" + "A" * 29,
    ],
)
def test_create_bot_rejects_invalid_token(
    bootstrap_module: tuple[object, ...], monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    """Create bot rejects invalid token."""
    bootstrap, created_tokens = bootstrap_module
    monkeypatch.setattr(bootstrap.config, "BOT_TOKEN", token)

    with pytest.raises(RuntimeError, match="BOT_TOKEN имеет неверный формат"):
        bootstrap.create_bot()

    assert created_tokens == []


def test_create_bot_accepts_token_with_expected_format(
    bootstrap_module: tuple[object, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Create bot accepts token with expected format."""
    bootstrap, created_tokens = bootstrap_module
    token = "123456789:" + "A_b-9" * 7
    monkeypatch.setattr(bootstrap.config, "BOT_TOKEN", token)

    bot = bootstrap.create_bot()

    assert bot.token == token
    assert created_tokens == [token]
