# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for application composition and resource lifecycle."""

import asyncio
import logging
import os
from types import SimpleNamespace

import pytest

import bot.app.routers as app_routers
import bot.main as main_module
from bot.app import bootstrap, lifecycle
from bot.app.background import image_cleanup
from bot.config.settings import ConfigError, Settings
from tests.support.settings import make_settings

SETTINGS = make_settings()


class _FakeRouterDispatcher:
    def __init__(self) -> None:
        self.middleware_calls: list[object] = []
        self.routers: list[object] = []
        self.workflow_data: dict[str, object] = {}
        self.message = SimpleNamespace(middleware=self.middleware_calls.append)

    def include_router(self, router: object) -> None:
        self.routers.append(router)


class _FakeThrottleMiddleware:
    pass


class _FakeAccessMiddleware:
    pass


class _FakeCleanupMiddleware:
    pass


def test_dispatcher_registers_middlewares_and_routers_once_in_original_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dispatcher registers middlewares and routers once in original order."""
    router_refs = {name: object() for name in ("start", "admin", "commands", "chat")}
    for name, router in router_refs.items():
        monkeypatch.setattr(app_routers, name, SimpleNamespace(router=router))
    monkeypatch.setattr(app_routers, "ThrottleMiddleware", _FakeThrottleMiddleware)
    monkeypatch.setattr(app_routers, "AccessMiddleware", _FakeAccessMiddleware)
    monkeypatch.setattr(
        app_routers,
        "TemporaryMessagesCleanupMiddleware",
        _FakeCleanupMiddleware,
    )

    dispatcher = _FakeRouterDispatcher()
    configured = app_routers.configure_dispatcher(dispatcher, SETTINGS)

    assert configured is dispatcher
    assert dispatcher.workflow_data["settings"] is SETTINGS
    assert len(dispatcher.middleware_calls) == 3
    assert isinstance(dispatcher.middleware_calls[0], _FakeThrottleMiddleware)
    assert isinstance(dispatcher.middleware_calls[1], _FakeAccessMiddleware)
    assert isinstance(dispatcher.middleware_calls[2], _FakeCleanupMiddleware)
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
    calls: list[dict[str, object]] = []

    class FakeDatabase:
        async def cleanup_old_images(self, **kwargs: object) -> dict[str, object]:
            calls.append(kwargs)
            return {"old_images": 1, "orphan_images": 2, "failed": 0}

    async def stop_after_first_iteration(_delay: object) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(image_cleanup, "db", FakeDatabase())
    monkeypatch.setattr(image_cleanup.asyncio, "sleep", stop_after_first_iteration)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(image_cleanup.periodic_image_cleanup())

    assert calls == [{"retention_days": 30, "orphan_grace_hours": 24}]
    assert image_cleanup.IMAGE_CLEANUP_INTERVAL == 24 * 60 * 60


def test_periodic_cleanup_continues_after_database_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Periodic cleanup continues after a failed iteration."""
    calls: list[dict[str, object]] = []
    sleep_calls = 0

    class FakeDatabase:
        async def cleanup_old_images(self, **kwargs: object) -> dict[str, object]:
            calls.append(kwargs)
            if len(calls) == 1:
                msg = "temporary database failure"
                raise RuntimeError(msg)
            return {"old_images": 0, "orphan_images": 0, "failed": 0}

    async def stop_after_retry(_delay: object) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(image_cleanup, "db", FakeDatabase())
    monkeypatch.setattr(image_cleanup.asyncio, "sleep", stop_after_retry)

    with (
        caplog.at_level(logging.ERROR, logger="bot.main"),
        pytest.raises(asyncio.CancelledError),
    ):
        asyncio.run(image_cleanup.periodic_image_cleanup())

    assert calls == [
        {"retention_days": 30, "orphan_grace_hours": 24},
        {"retention_days": 30, "orphan_grace_hours": 24},
    ]
    assert sleep_calls == 2
    assert "Scheduled image cleanup failed" in caplog.text


class _LifecycleHarness:
    """Record the order of resource calls made by ``run_application``."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.db = _FakeDatabase(self.calls)
        self.llm = _FakeLLM(self.calls)
        self.bot = _FakeBot(self.calls)
        self.dispatcher = _FakeDispatcher(self.calls)


class _FakeBot:
    def __init__(self, calls: list[str]) -> None:
        async def close_session() -> None:
            calls.append("telegram.close")

        self.session = SimpleNamespace(close=close_session)


class _FakeDispatcher:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def start_polling(self, bot: object, **kwargs: object) -> None:
        assert isinstance(bot, _FakeBot)
        assert kwargs == {"close_bot_session": False}
        self.calls.append("polling")
        # Let the just-created background task start before polling returns.
        await asyncio.sleep(0)


class _FakeDatabase:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.settings: Settings | None = None

    def configure(self, settings: Settings) -> None:
        self.settings = settings
        self.calls.append("db.configure")

    async def connect(self) -> None:
        self.calls.append("db.connect")

    async def close(self) -> None:
        self.calls.append("db.close")


class _FakeLLM:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.settings: Settings | None = None

    def configure(self, settings: Settings) -> None:
        self.settings = settings
        self.calls.append("llm.configure")

    async def start(self) -> None:
        self.calls.append("llm.start")

    async def close(self) -> None:
        self.calls.append("llm.close")


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> _LifecycleHarness:
    """Replace the lifecycle resources with recording fakes."""
    result = _LifecycleHarness()

    async def fake_periodic_cleanup() -> None:
        result.calls.append("cleanup.start")
        try:
            await asyncio.Future()
        finally:
            result.calls.append("cleanup.stop")

    monkeypatch.setattr(lifecycle, "db", result.db)
    monkeypatch.setattr(lifecycle, "llm_client", result.llm)
    monkeypatch.setattr(lifecycle, "periodic_image_cleanup", fake_periodic_cleanup)
    return result


def test_lifecycle_preserves_startup_polling_and_shutdown_order(
    harness: _LifecycleHarness,
) -> None:
    """Lifecycle configures resources first, then starts and stops them in order."""
    asyncio.run(lifecycle.run_application(harness.bot, harness.dispatcher, SETTINGS))

    assert harness.db.settings is SETTINGS
    assert harness.llm.settings is SETTINGS
    assert harness.calls == [
        "db.configure",
        "llm.configure",
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
    harness: _LifecycleHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lifecycle closes remaining resources when startup fails."""

    async def fail_connect() -> None:
        harness.calls.append("db.connect")
        msg = "database unavailable"
        raise RuntimeError(msg)

    monkeypatch.setattr(harness.db, "connect", fail_connect)

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(
            lifecycle.run_application(harness.bot, harness.dispatcher, SETTINGS)
        )

    assert harness.calls == [
        "db.configure",
        "llm.configure",
        "db.connect",
        "llm.close",
        "db.close",
        "telegram.close",
    ]


def test_lifecycle_continues_closing_after_one_cleanup_error(
    harness: _LifecycleHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lifecycle continues closing after one cleanup error."""

    async def fail_llm_close() -> None:
        harness.calls.append("llm.close")
        msg = "LLM close failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(harness.llm, "close", fail_llm_close)

    asyncio.run(lifecycle.run_application(harness.bot, harness.dispatcher, SETTINGS))

    assert harness.calls[-3:] == ["llm.close", "db.close", "telegram.close"]


def test_lifecycle_cancels_running_request_and_background_task_on_shutdown(
    harness: _LifecycleHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lifecycle shuts down resources when polling is cancelled during a request."""
    request_started = asyncio.Event()
    request_cancelled = asyncio.Event()

    async def blocked_polling(_bot: object, **_kwargs: object) -> None:
        harness.calls.append("polling")
        await asyncio.sleep(0)
        request_started.set()
        try:
            await asyncio.Future()
        finally:
            harness.calls.append("request.cancelled")
            request_cancelled.set()

    monkeypatch.setattr(harness.dispatcher, "start_polling", blocked_polling)

    async def cancel_application() -> None:
        application_task = asyncio.create_task(
            lifecycle.run_application(harness.bot, harness.dispatcher, SETTINGS)
        )
        await request_started.wait()
        application_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await application_task

    asyncio.run(cancel_application())

    assert request_cancelled.is_set()
    assert harness.calls == [
        "db.configure",
        "llm.configure",
        "db.connect",
        "llm.start",
        "polling",
        "cleanup.start",
        "request.cancelled",
        "cleanup.stop",
        "llm.close",
        "db.close",
        "telegram.close",
    ]


def _patch_main_components(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[object],
) -> None:
    """Replace every side effect of ``bootstrap.main`` with a recorder."""
    monkeypatch.setattr(
        bootstrap.os, "umask", lambda mask: calls.append(("umask", mask))
    )
    monkeypatch.setattr(bootstrap, "load_env_file", lambda: calls.append("env"))
    monkeypatch.setattr(
        bootstrap,
        "configure_logging",
        lambda settings: calls.append(("logging", settings)),
    )
    monkeypatch.setattr(
        bootstrap,
        "configure_pillow_limits",
        lambda: calls.append("pillow_limits"),
    )
    monkeypatch.setattr(
        bootstrap,
        "log_access_mode",
        lambda settings: calls.append(("access_mode", settings)),
    )


def test_bootstrap_main_loads_env_and_passes_settings_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bootstrap main loads the env file once and passes one Settings object down."""
    calls: list[object] = []
    bot_instance = object()
    dispatcher_instance = object()
    _patch_main_components(monkeypatch, calls)

    def load_settings(environ: object) -> Settings:
        assert environ is os.environ
        calls.append("settings")
        return SETTINGS

    def create_bot(settings: Settings) -> object:
        calls.append(("bot", settings))
        return bot_instance

    def create_dispatcher(settings: Settings) -> object:
        calls.append(("dispatcher", settings))
        return dispatcher_instance

    async def run_application(
        bot: object,
        dispatcher: object,
        settings: Settings,
    ) -> None:
        assert bot is bot_instance
        assert dispatcher is dispatcher_instance
        calls.append(("run", settings))

    monkeypatch.setattr(bootstrap, "load_settings", load_settings)
    monkeypatch.setattr(bootstrap, "create_bot", create_bot)
    monkeypatch.setattr(bootstrap, "create_dispatcher", create_dispatcher)
    monkeypatch.setattr(bootstrap, "run_application", run_application)

    asyncio.run(bootstrap.main())

    assert calls == [
        ("umask", 0o077),
        "env",
        "settings",
        ("logging", SETTINGS),
        "pillow_limits",
        ("access_mode", SETTINGS),
        ("bot", SETTINGS),
        ("dispatcher", SETTINGS),
        ("run", SETTINGS),
    ]


def test_bootstrap_main_stops_on_invalid_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid environment settings abort startup before any component starts."""
    calls: list[object] = []
    _patch_main_components(monkeypatch, calls)
    monkeypatch.delenv("SUPERVISOR_ID", raising=False)

    with pytest.raises(ConfigError, match="SUPERVISOR_ID"):
        asyncio.run(bootstrap.main())

    assert calls == [("umask", 0o077), "env"]


def test_create_dispatcher_passes_settings_to_router_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create dispatcher hands the same Settings object to the router wiring."""

    class FakeDispatcher:
        pass

    def configure_dispatcher(dispatcher: object, settings: Settings) -> object:
        assert isinstance(dispatcher, FakeDispatcher)
        assert settings is SETTINGS
        return dispatcher

    monkeypatch.setattr(bootstrap, "Dispatcher", FakeDispatcher)
    monkeypatch.setattr(bootstrap, "configure_dispatcher", configure_dispatcher)

    assert isinstance(bootstrap.create_dispatcher(SETTINGS), FakeDispatcher)


def test_main_module_is_a_thin_entrypoint() -> None:
    """Main module exposes only the bootstrap entrypoint."""
    assert main_module.main is bootstrap.main
    assert main_module.__all__ == ["main"]


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
    caplog: pytest.LogCaptureFixture,
    allow_all: object,
    allowed_users: object,
    expected_message: str,
    expected_level: str,
) -> None:
    """Log access mode reports configured mode."""
    settings = make_settings(ALLOW_ALL_USERS=allow_all, ALLOWED_USERS=allowed_users)

    with caplog.at_level(logging.DEBUG, logger="bot.main"):
        bootstrap.log_access_mode(settings)

    assert any(
        record.levelname == expected_level and expected_message in record.message
        for record in caplog.records
    )


@pytest.fixture
def created_tokens(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the Telegram Bot class with a recorder of created tokens."""
    tokens: list[str] = []

    class FakeBot:
        def __init__(self, token: str) -> None:
            self.token = token
            tokens.append(token)

    monkeypatch.setattr(bootstrap, "Bot", FakeBot)
    return tokens


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
    created_tokens: list[str],
    token: str,
) -> None:
    """Create bot rejects invalid token."""
    settings = make_settings(BOT_TOKEN=token)

    with pytest.raises(RuntimeError, match="BOT_TOKEN имеет неверный формат"):
        bootstrap.create_bot(settings)

    assert created_tokens == []


def test_create_bot_accepts_token_with_expected_format(
    created_tokens: list[str],
) -> None:
    """Create bot accepts token with expected format."""
    token = "123456789:" + "A_b-9" * 7
    settings = make_settings(BOT_TOKEN=token)

    bot = bootstrap.create_bot(settings)

    assert bot.token == token
    assert created_tokens == [token]
