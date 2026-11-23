# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for application composition and resource lifecycle."""

import asyncio
import logging
import os
from types import SimpleNamespace

import pytest

import bot_obormot.app.routers as app_routers
import bot_obormot.main as main_module
from bot_obormot.app import bootstrap, lifecycle
from bot_obormot.app.background import image_cleanup
from bot_obormot.middlewares.access import AccessMiddleware
from bot_obormot.middlewares.temporary_messages import (
    TemporaryMessagesCleanupMiddleware,
)
from bot_obormot.middlewares.throttle import ThrottleMiddleware
from bot_obormot.services.chat.aggregation import MessageAggregator
from bot_obormot.settings import ConfigError, Settings
from tests.support.lifecycle import (
    FakeLifecycleLLM,
    FakeRouterDispatcher,
    LifecycleHarness,
)
from tests.support.settings import make_settings

SETTINGS = make_settings()


def test_dispatcher_registers_middlewares_and_routers_once_in_original_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dispatcher registers middlewares and routers once in original order."""
    router_refs = {name: object() for name in ("start", "admin", "routers", "chat")}
    for name, router in router_refs.items():
        monkeypatch.setattr(app_routers, name, SimpleNamespace(router=router))

    dispatcher = FakeRouterDispatcher()
    llm_client = FakeLifecycleLLM([])
    message_aggregator = MessageAggregator()
    database = object()
    configured = app_routers.configure_dispatcher(
        dispatcher,
        SETTINGS,
        llm_client,
        message_aggregator,
        database,
    )

    assert configured is dispatcher
    assert dispatcher.workflow_data["settings"] is SETTINGS
    assert dispatcher.workflow_data["llm_client"] is llm_client
    assert dispatcher.workflow_data["message_aggregator"] is message_aggregator
    assert dispatcher.workflow_data["database"] is database
    expected_count = 3
    assert len(dispatcher.middleware_calls) == expected_count
    assert isinstance(dispatcher.middleware_calls[0], ThrottleMiddleware)
    assert isinstance(dispatcher.middleware_calls[1], AccessMiddleware)
    assert isinstance(
        dispatcher.middleware_calls[2], TemporaryMessagesCleanupMiddleware
    )
    assert dispatcher.routers == [
        router_refs["start"],
        router_refs["admin"],
        router_refs["routers"],
        router_refs["chat"],
    ]


def test_periodic_cleanup_uses_existing_policy_and_propagates_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Periodic cleanup uses existing policy and propagates cancellation."""
    calls: list[dict[str, object]] = []

    async def cleanup_old_images(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"old_images": 1, "orphan_images": 2, "failed": 0}

    database = SimpleNamespace(cleanup_old_images=cleanup_old_images)

    async def stop_after_first_iteration(_delay: object) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(image_cleanup.asyncio, "sleep", stop_after_first_iteration)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(image_cleanup.periodic_image_cleanup(database))

    assert calls == [{"retention_days": 30, "orphan_grace_hours": 24}]
    assert image_cleanup.IMAGE_CLEANUP_INTERVAL == 24 * 60 * 60


def test_periodic_cleanup_continues_after_database_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Periodic cleanup continues after a failed iteration."""
    calls: list[dict[str, object]] = []
    sleep_calls = 0

    async def cleanup_old_images(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        if len(calls) == 1:
            msg = "temporary database failure"
            raise RuntimeError(msg)
        return {"old_images": 0, "orphan_images": 0, "failed": 0}

    database = SimpleNamespace(cleanup_old_images=cleanup_old_images)

    async def stop_after_retry(_delay: object) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        expected_sleep_calls = 2
        if sleep_calls == expected_sleep_calls:
            raise asyncio.CancelledError

    monkeypatch.setattr(image_cleanup.asyncio, "sleep", stop_after_retry)

    with (
        caplog.at_level(logging.ERROR, logger="bot_obormot.main"),
        pytest.raises(asyncio.CancelledError),
    ):
        asyncio.run(image_cleanup.periodic_image_cleanup(database))

    assert calls == [
        {"retention_days": 30, "orphan_grace_hours": 24},
        {"retention_days": 30, "orphan_grace_hours": 24},
    ]
    expected_sleep_calls = 2
    assert sleep_calls == expected_sleep_calls
    expected_fragment = "Scheduled image cleanup failed"
    assert expected_fragment in caplog.text


@pytest.fixture(name="harness")
def fixture_harness(monkeypatch: pytest.MonkeyPatch) -> LifecycleHarness:
    """Replace the lifecycle resources with recording fakes."""
    result = LifecycleHarness()

    async def fake_periodic_cleanup(database: object) -> None:
        assert database is result.database
        result.calls.append("cleanup.start")
        try:
            await asyncio.Future()
        finally:
            result.calls.append("cleanup.stop")

    monkeypatch.setattr(
        lifecycle,
        "periodic_image_cleanup",
        fake_periodic_cleanup,
    )
    return result


def test_lifecycle_preserves_startup_polling_and_shutdown_order(
    harness: LifecycleHarness,
) -> None:
    """Lifecycle starts and stops resources in the expected order."""
    asyncio.run(
        lifecycle.run_application(
            harness.bot,
            harness.dispatcher,
            harness.llm,
            harness.database,
        )
    )

    assert harness.calls == [
        "database.connect",
        "llm.start",
        "polling",
        "cleanup.start",
        "cleanup.stop",
        "database.close",
        "llm.close",
        "telegram.close",
    ]


def test_lifecycle_closes_database_and_resources_when_llm_startup_fails(
    harness: LifecycleHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lifecycle closes the database and remaining resources when LLM startup fails."""

    async def fail_start() -> None:
        harness.calls.append("llm.start")
        msg = "LLM startup failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(harness.llm, "start", fail_start)

    with pytest.raises(RuntimeError, match="LLM startup failed"):
        asyncio.run(
            lifecycle.run_application(
                harness.bot,
                harness.dispatcher,
                harness.llm,
                harness.database,
            )
        )

    assert harness.calls == [
        "database.connect",
        "llm.start",
        "database.close",
        "llm.close",
        "telegram.close",
    ]


def test_lifecycle_closes_remaining_resources_when_database_startup_fails(
    harness: LifecycleHarness,
) -> None:
    """Lifecycle closes remaining resources when database startup fails."""
    harness.database.fail_on_enter = True

    with pytest.raises(RuntimeError, match="application database unavailable"):
        asyncio.run(
            lifecycle.run_application(
                harness.bot,
                harness.dispatcher,
                harness.llm,
                harness.database,
            )
        )

    assert harness.calls == [
        "database.connect",
        "llm.close",
        "telegram.close",
    ]


def test_lifecycle_continues_closing_after_one_cleanup_error(
    harness: LifecycleHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lifecycle continues closing after one cleanup error."""

    async def fail_llm_close() -> None:
        harness.calls.append("llm.close")
        msg = "LLM close failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(harness.llm, "close", fail_llm_close)

    asyncio.run(
        lifecycle.run_application(
            harness.bot,
            harness.dispatcher,
            harness.llm,
            harness.database,
        )
    )

    assert harness.calls[-2:] == ["llm.close", "telegram.close"]


def test_lifecycle_cancels_running_request_and_background_task_on_shutdown(
    harness: LifecycleHarness,
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
            lifecycle.run_application(
                harness.bot,
                harness.dispatcher,
                harness.llm,
                harness.database,
            )
        )
        await request_started.wait()
        application_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await application_task

    asyncio.run(cancel_application())

    assert request_cancelled.is_set()
    assert harness.calls == [
        "database.connect",
        "llm.start",
        "polling",
        "cleanup.start",
        "request.cancelled",
        "cleanup.stop",
        "database.close",
        "llm.close",
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
    monkeypatch.setattr(
        bootstrap, "load_env_file", lambda _env_file=None: calls.append("env")
    )
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
    aggregator_instance = object()
    database_instance = object()
    _patch_main_components(monkeypatch, calls)
    llm_instance = FakeLifecycleLLM(calls)

    def load_settings(environ: object) -> Settings:
        assert environ is os.environ
        calls.append("settings")
        return SETTINGS

    def create_message_aggregator() -> object:
        calls.append("message_aggregator")
        return aggregator_instance

    def create_database(settings: Settings) -> object:
        calls.append(("database", settings))
        return database_instance

    def create_llm_client(settings: Settings) -> FakeLifecycleLLM:
        calls.append(("llm_client", settings))
        return llm_instance

    def create_bot(settings: Settings) -> object:
        calls.append(("bot", settings))
        return bot_instance

    def create_dispatcher(
        settings: Settings,
        llm_client: FakeLifecycleLLM,
        message_aggregator: object,
        database: object,
    ) -> object:
        calls.append(("dispatcher", settings, llm_client, message_aggregator, database))
        return dispatcher_instance

    async def run_application(
        bot: object,
        dispatcher: object,
        llm_client: FakeLifecycleLLM,
        database: object,
    ) -> None:
        assert bot is bot_instance
        assert dispatcher is dispatcher_instance
        assert llm_client is llm_instance
        assert database is database_instance
        calls.append("run")

    monkeypatch.setattr(bootstrap, "load_settings", load_settings)
    monkeypatch.setattr(bootstrap, "LLMClient", create_llm_client)
    monkeypatch.setattr(bootstrap, "MessageAggregator", create_message_aggregator)
    monkeypatch.setattr(bootstrap, "Database", create_database)
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
        ("llm_client", SETTINGS),
        "message_aggregator",
        ("database", SETTINGS),
        ("dispatcher", SETTINGS, llm_instance, aggregator_instance, database_instance),
        "run",
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
    outer_middlewares: list[object] = []
    created = SimpleNamespace(
        update=SimpleNamespace(outer_middleware=outer_middlewares.append),
    )

    llm_client = FakeLifecycleLLM([])
    message_aggregator = MessageAggregator()
    database = object()

    def configure_dispatcher(
        dispatcher: object,
        settings: Settings,
        configured_llm: FakeLifecycleLLM,
        configured_aggregator: MessageAggregator,
        configured_database: object,
    ) -> object:
        assert dispatcher is created
        assert settings is SETTINGS
        assert configured_llm is llm_client
        assert configured_aggregator is message_aggregator
        assert configured_database is database
        return dispatcher

    monkeypatch.setattr(bootstrap, "Dispatcher", lambda: created)
    monkeypatch.setattr(bootstrap, "configure_dispatcher", configure_dispatcher)

    dispatcher = bootstrap.create_dispatcher(
        SETTINGS, llm_client, message_aggregator, database
    )

    assert dispatcher is created
    assert len(outer_middlewares) == 1
    assert isinstance(outer_middlewares[0], bootstrap.CorrelationIdMiddleware)


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

    with caplog.at_level(logging.DEBUG, logger="bot_obormot.main"):
        bootstrap.log_access_mode(settings)

    assert any(
        record.levelname == expected_level and expected_message in record.message
        for record in caplog.records
    )


@pytest.fixture(name="created_tokens")
def fixture_created_tokens(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the Telegram Bot class with a recorder of created tokens."""
    tokens: list[str] = []

    def create_bot(token: str) -> SimpleNamespace:
        tokens.append(token)
        return SimpleNamespace(token=token)

    monkeypatch.setattr(bootstrap, "Bot", create_bot)
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

    with pytest.raises(RuntimeError, match="BOT_TOKEN has an invalid format"):
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
