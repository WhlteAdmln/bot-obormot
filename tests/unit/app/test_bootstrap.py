# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for application composition and resource lifecycle."""

import asyncio
import logging
import os
from collections.abc import Iterable
from types import SimpleNamespace

import pytest

import bot_obormot.app.routers as app_routers
import bot_obormot.main as main_module
from bot_obormot.app import bootstrap, lifecycle
from bot_obormot.app.background import image_cleanup
from bot_obormot.middlewares.access import AccessMiddleware
from bot_obormot.middlewares.correlation_id import CorrelationIdMiddleware
from bot_obormot.middlewares.temporary_messages import (
    TemporaryMessagesCleanupMiddleware,
)
from bot_obormot.middlewares.throttle import ThrottleMiddleware
from bot_obormot.services.chat.aggregation import MessageAggregator
from bot_obormot.services.chat.locks import UserLocks
from bot_obormot.settings import ConfigError, Settings
from tests.support.lifecycle import (
    FakeLifecycleLLM,
    FakeRouterDispatcher,
    LifecycleHarness,
)
from tests.support.settings import make_settings


def _identities(values: Iterable[object]) -> list[int]:
    """Return the identities of the values, to compare objects by identity."""
    return [id(value) for value in values]


@pytest.fixture(name="settings")
def fixture_settings() -> Settings:
    """Return valid settings for one test."""
    return make_settings()


@pytest.fixture(name="configured")
def fixture_configured(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> SimpleNamespace:
    """Configure a recording dispatcher with stand-in routers."""
    router_refs = {name: object() for name in ("start", "admin", "routers", "chat")}
    for name, router in router_refs.items():
        stand_in = SimpleNamespace(create_router=lambda router=router: router)
        monkeypatch.setattr(app_routers, name, stand_in)
    dispatcher = FakeRouterDispatcher()
    llm_client = FakeLifecycleLLM([])
    message_aggregator = MessageAggregator()
    database = object()
    result = app_routers.configure_dispatcher(
        dispatcher,
        settings,
        llm_client,
        message_aggregator,
        database,
    )
    return SimpleNamespace(
        result=result,
        dispatcher=dispatcher,
        settings=settings,
        llm_client=llm_client,
        message_aggregator=message_aggregator,
        database=database,
        router_refs=router_refs,
    )


def test_configure_dispatcher_returns_the_given_dispatcher(
    configured: SimpleNamespace,
) -> None:
    assert configured.result is configured.dispatcher, "another dispatcher returned"


@pytest.mark.parametrize("key", ["settings", "llm_client", "database"])
def test_configure_dispatcher_stores_dependency_in_workflow_data(
    configured: SimpleNamespace,
    key: str,
) -> None:
    stored = configured.dispatcher.workflow_data[key]
    assert stored is getattr(configured, key), f"workflow data holds another {key}"


def test_configure_dispatcher_gives_handlers_the_message_aggregator(
    configured: SimpleNamespace,
) -> None:
    runtime = configured.dispatcher.workflow_data["chat_runtime"]
    expected = configured.message_aggregator
    assert runtime.message_aggregator is expected, "handlers got another aggregator"


def test_configure_dispatcher_registers_middlewares_once_in_original_order(
    configured: SimpleNamespace,
) -> None:
    expected_types = [
        ThrottleMiddleware,
        AccessMiddleware,
        TemporaryMessagesCleanupMiddleware,
    ]
    registered = [type(item) for item in configured.dispatcher.middleware_calls]
    assert registered == expected_types, "middlewares differ in kind or order"


def test_configure_dispatcher_includes_routers_once_in_original_order(
    configured: SimpleNamespace,
) -> None:
    refs = configured.router_refs
    expected_routers = [refs["start"], refs["admin"], refs["routers"], refs["chat"]]
    routers = configured.dispatcher.routers
    assert routers == expected_routers, "routers differ in identity or order"


def test_configure_dispatcher_shares_given_user_locks_with_handlers(
    settings: Settings,
) -> None:
    dispatcher = FakeRouterDispatcher()
    user_locks = UserLocks()

    app_routers.configure_dispatcher(dispatcher, settings, user_locks=user_locks)

    stored = dispatcher.workflow_data["chat_runtime"].user_locks
    assert stored is user_locks, "handlers must receive the user locks of the app"


def test_configure_dispatcher_creates_user_locks_when_none_is_given(
    settings: Settings,
) -> None:
    dispatcher = FakeRouterDispatcher()

    app_routers.configure_dispatcher(dispatcher, settings)

    stored = dispatcher.workflow_data["chat_runtime"].user_locks
    assert isinstance(stored, UserLocks), "handlers must always receive user locks"


def test_configure_dispatcher_gives_each_dispatcher_its_own_downloader(
    settings: Settings,
) -> None:
    first = FakeRouterDispatcher()
    second = FakeRouterDispatcher()

    app_routers.configure_dispatcher(first, settings)
    app_routers.configure_dispatcher(second, settings)

    first_downloader = first.workflow_data["chat_runtime"].downloader
    second_downloader = second.workflow_data["chat_runtime"].downloader
    assert first_downloader is not second_downloader, "bots must not share slots"


def test_configure_dispatcher_gives_each_dispatcher_its_own_media_slots(
    settings: Settings,
) -> None:
    first = FakeRouterDispatcher()
    second = FakeRouterDispatcher()

    app_routers.configure_dispatcher(first, settings)
    app_routers.configure_dispatcher(second, settings)

    first_slots = first.workflow_data["chat_runtime"].media_slots
    second_slots = second.workflow_data["chat_runtime"].media_slots
    assert first_slots is not second_slots, "bots must not share media slots"


def _run_one_cleanup_iteration(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Run the periodic cleanup until its first sleep and record what it did."""
    record = SimpleNamespace(calls=[], delays=[])

    async def cleanup_old_images(**kwargs: object) -> dict[str, object]:
        record.calls.append(kwargs)
        return {"old_images": 1, "orphan_images": 2, "failed": 0}

    async def stop_after_first_iteration(delay: object) -> None:
        record.delays.append(delay)
        raise asyncio.CancelledError

    database = SimpleNamespace(cleanup_old_images=cleanup_old_images)
    monkeypatch.setattr(image_cleanup.asyncio, "sleep", stop_after_first_iteration)
    with pytest.raises(asyncio.CancelledError) as excinfo:
        asyncio.run(image_cleanup.periodic_image_cleanup(database))
    record.error_type = excinfo.type
    return record


def test_periodic_cleanup_uses_existing_retention_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_calls = [{"retention_days": 30, "orphan_grace_hours": 24}]
    record = _run_one_cleanup_iteration(monkeypatch)
    assert record.calls == expected_calls, "cleanup used another retention policy"


def test_periodic_cleanup_waits_one_day_between_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_delays = [24 * 60 * 60]
    record = _run_one_cleanup_iteration(monkeypatch)
    assert record.delays == expected_delays, "cleanup waits another interval"


def test_periodic_cleanup_interval_is_one_day() -> None:
    one_day = 24 * 60 * 60
    interval = image_cleanup.IMAGE_CLEANUP_INTERVAL
    assert interval == one_day, "the cleanup interval is not one day"


def test_periodic_cleanup_propagates_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _run_one_cleanup_iteration(monkeypatch)
    assert record.error_type is asyncio.CancelledError, "cancellation was swallowed"


def _run_cleanup_with_one_failure(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Run the periodic cleanup whose first run fails, until its second sleep."""
    record = SimpleNamespace(calls=[], sleep_calls=0)
    expected_sleep_calls = 2

    async def cleanup_old_images(**kwargs: object) -> dict[str, object]:
        record.calls.append(kwargs)
        if len(record.calls) == 1:
            msg = "temporary database failure"
            raise RuntimeError(msg)
        return {"old_images": 0, "orphan_images": 0, "failed": 0}

    async def stop_after_retry(_delay: object) -> None:
        record.sleep_calls += 1
        if record.sleep_calls == expected_sleep_calls:
            raise asyncio.CancelledError

    database = SimpleNamespace(cleanup_old_images=cleanup_old_images)
    monkeypatch.setattr(image_cleanup.asyncio, "sleep", stop_after_retry)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(image_cleanup.periodic_image_cleanup(database))
    return record


def test_periodic_cleanup_retries_after_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_calls = [
        {"retention_days": 30, "orphan_grace_hours": 24},
        {"retention_days": 30, "orphan_grace_hours": 24},
    ]
    record = _run_cleanup_with_one_failure(monkeypatch)
    assert record.calls == expected_calls, "cleanup did not run again after an error"


def test_periodic_cleanup_keeps_sleeping_after_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_sleep_calls = 2
    record = _run_cleanup_with_one_failure(monkeypatch)
    assert record.sleep_calls == expected_sleep_calls, "cleanup stopped sleeping"


def test_periodic_cleanup_logs_database_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cleanup_error = "Scheduled image cleanup failed"
    with caplog.at_level(logging.ERROR, logger="bot_obormot.main"):
        _run_cleanup_with_one_failure(monkeypatch)
    assert cleanup_error in caplog.text, "the cleanup error was not logged"


@pytest.fixture(name="harness")
def fixture_harness(monkeypatch: pytest.MonkeyPatch) -> LifecycleHarness:
    """Replace the lifecycle resources with recording fakes."""
    result = LifecycleHarness()

    async def fake_periodic_cleanup(database: object) -> None:
        own_database = database is result.database
        result.calls.append("cleanup.start" if own_database else "cleanup.foreign")
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
    expected_calls = [
        "database.connect",
        "llm.start",
        "polling",
        "cleanup.start",
        "cleanup.stop",
        "database.close",
        "llm.close",
        "telegram.close",
    ]

    asyncio.run(
        lifecycle.run_application(
            harness.bot,
            harness.dispatcher,
            harness.llm,
            harness.database,
        )
    )

    assert harness.calls == expected_calls, "lifecycle steps ran in another order"


def test_lifecycle_closes_database_and_resources_when_llm_startup_fails(
    harness: LifecycleHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_calls = [
        "database.connect",
        "llm.start",
        "database.close",
        "llm.close",
        "telegram.close",
    ]

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

    assert harness.calls == expected_calls, "resources were not closed after failure"


def test_lifecycle_closes_remaining_resources_when_database_startup_fails(
    harness: LifecycleHarness,
) -> None:
    expected_calls = ["database.connect", "llm.close", "telegram.close"]
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

    assert harness.calls == expected_calls, "remaining resources were not closed"


def test_lifecycle_continues_closing_after_one_cleanup_error(
    harness: LifecycleHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_tail = ["llm.close", "telegram.close"]

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

    assert harness.calls[-2:] == expected_tail, "closing stopped after an error"


def _cancel_running_application(
    harness: LifecycleHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> asyncio.Event:
    """Cancel the application while a request is running; return its cancel flag."""
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
    return request_cancelled


def test_lifecycle_cancels_running_request_on_shutdown(
    harness: LifecycleHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_cancelled = _cancel_running_application(harness, monkeypatch)
    assert request_cancelled.is_set(), "the running request was not cancelled"


def test_lifecycle_stops_background_task_and_closes_resources_on_shutdown(
    harness: LifecycleHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_calls = [
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
    _cancel_running_application(harness, monkeypatch)
    assert harness.calls == expected_calls, "shutdown steps ran in another order"


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
    monkeypatch.setattr(bootstrap, "log_tgs_support", lambda: calls.append("tgs"))
    monkeypatch.setattr(
        bootstrap,
        "log_access_mode",
        lambda settings: calls.append(("access_mode", settings)),
    )


@pytest.fixture(name="main_run")
def fixture_main_run(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> SimpleNamespace:
    """Run ``bootstrap.main`` with recording components and return the record."""
    record = SimpleNamespace(
        calls=[],
        environs=[],
        run_args=[],
        settings=settings,
        bot=object(),
        dispatcher=object(),
        aggregator=object(),
        database=object(),
    )
    _patch_main_components(monkeypatch, record.calls)
    llm = FakeLifecycleLLM(record.calls)
    record.llm = llm

    def load_settings(environ: object) -> Settings:
        record.environs.append(environ)
        record.calls.append("settings")
        return settings

    def create_message_aggregator() -> object:
        record.calls.append("message_aggregator")
        return record.aggregator

    def create_database(given: Settings) -> object:
        record.calls.append(("database", given))
        return record.database

    def create_llm_client(given: Settings) -> FakeLifecycleLLM:
        record.calls.append(("llm_client", given))
        return llm

    def create_bot(given: Settings) -> object:
        record.calls.append(("bot", given))
        return record.bot

    def create_dispatcher(
        given: Settings,
        llm_client: FakeLifecycleLLM,
        message_aggregator: object,
        database: object,
        _user_locks: UserLocks,
    ) -> object:
        record.calls.append(
            ("dispatcher", given, llm_client, message_aggregator, database)
        )
        return record.dispatcher

    async def run_application(
        bot: object,
        dispatcher: object,
        llm_client: FakeLifecycleLLM,
        database: object,
    ) -> None:
        record.run_args.extend([bot, dispatcher, llm_client, database])
        record.calls.append("run")

    monkeypatch.setattr(bootstrap, "load_settings", load_settings)
    monkeypatch.setattr(bootstrap, "LLMClient", create_llm_client)
    monkeypatch.setattr(bootstrap, "MessageAggregator", create_message_aggregator)
    monkeypatch.setattr(bootstrap, "Database", create_database)
    monkeypatch.setattr(bootstrap, "create_bot", create_bot)
    monkeypatch.setattr(bootstrap, "create_dispatcher", create_dispatcher)
    monkeypatch.setattr(bootstrap, "run_application", run_application)

    asyncio.run(bootstrap.main())
    return record


def test_bootstrap_main_loads_env_and_passes_settings_down(
    main_run: SimpleNamespace,
) -> None:
    settings = main_run.settings
    expected_calls = [
        ("umask", 0o077),
        "env",
        "settings",
        ("logging", settings),
        "pillow_limits",
        "tgs",
        ("access_mode", settings),
        ("bot", settings),
        ("llm_client", settings),
        "message_aggregator",
        ("database", settings),
        (
            "dispatcher",
            settings,
            main_run.llm,
            main_run.aggregator,
            main_run.database,
        ),
        "run",
    ]
    assert main_run.calls == expected_calls, "main ran its steps in another order"


def test_bootstrap_main_reads_settings_from_process_environment(
    main_run: SimpleNamespace,
) -> None:
    expected = _identities([os.environ])
    received = _identities(main_run.environs)
    assert received == expected, "settings were not read from os.environ"


def test_bootstrap_main_runs_application_with_created_components(
    main_run: SimpleNamespace,
) -> None:
    expected = _identities(
        [main_run.bot, main_run.dispatcher, main_run.llm, main_run.database]
    )
    received = _identities(main_run.run_args)
    assert received == expected, "the application ran with other components"


def test_bootstrap_main_stops_on_invalid_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    expected_calls = [("umask", 0o077), "env"]
    _patch_main_components(monkeypatch, calls)
    monkeypatch.delenv("SUPERVISOR_ID", raising=False)

    with pytest.raises(ConfigError, match="SUPERVISOR_ID"):
        asyncio.run(bootstrap.main())

    assert calls == expected_calls, "main went on after invalid settings"


@pytest.fixture(name="created_dispatcher")
def fixture_created_dispatcher(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
) -> SimpleNamespace:
    """Create a dispatcher with a recording router configuration."""
    record = SimpleNamespace(outer_middlewares=[], configure_args=[])
    record.created = SimpleNamespace(
        update=SimpleNamespace(outer_middleware=record.outer_middlewares.append),
    )
    record.inputs = [
        settings,
        FakeLifecycleLLM([]),
        MessageAggregator(),
        object(),
        UserLocks(),
    ]

    def configure_dispatcher(dispatcher: object, *args: object) -> object:
        record.configure_args.extend([dispatcher, *args])
        return dispatcher

    monkeypatch.setattr(bootstrap, "Dispatcher", lambda: record.created)
    monkeypatch.setattr(bootstrap, "configure_dispatcher", configure_dispatcher)
    record.result = bootstrap.create_dispatcher(*record.inputs)
    return record


def test_create_dispatcher_passes_settings_to_router_configuration(
    created_dispatcher: SimpleNamespace,
) -> None:
    record = created_dispatcher
    expected = _identities([record.created, *record.inputs])
    received = _identities(record.configure_args)
    assert received == expected, "router configuration got other arguments"


def test_create_dispatcher_returns_the_configured_dispatcher(
    created_dispatcher: SimpleNamespace,
) -> None:
    record = created_dispatcher
    assert record.result is record.created, "another dispatcher was returned"


def test_create_dispatcher_adds_one_correlation_id_outer_middleware(
    created_dispatcher: SimpleNamespace,
) -> None:
    expected_types = [CorrelationIdMiddleware]
    registered = [type(item) for item in created_dispatcher.outer_middlewares]
    assert registered == expected_types, "outer middlewares differ"


def test_main_module_reexports_bootstrap_main() -> None:
    assert main_module.main is bootstrap.main, "main is not the bootstrap entry point"


def test_main_module_exports_only_main() -> None:
    expected_all = ["main"]
    assert main_module.__all__ == expected_all, "the entry point exports more names"


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
    settings = make_settings(ALLOW_ALL_USERS=allow_all, ALLOWED_USERS=allowed_users)

    with caplog.at_level(logging.DEBUG, logger="bot_obormot.main"):
        bootstrap.log_access_mode(settings)

    assert any(
        record.levelname == expected_level and expected_message in record.message
        for record in caplog.records
    ), "the access mode was not logged at the expected level"


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
    settings = make_settings(BOT_TOKEN=token)
    expected_empty: list[str] = []

    with pytest.raises(RuntimeError, match="BOT_TOKEN has an invalid format"):
        bootstrap.create_bot(settings)

    assert created_tokens == expected_empty, "a bot was created with an invalid token"


def test_create_bot_returns_bot_with_the_configured_token(
    created_tokens: list[str],
) -> None:
    token = "123456789:" + "A_b-9" * 7
    settings = make_settings(BOT_TOKEN=token)

    bot = bootstrap.create_bot(settings)

    assert bot.token == token, f"the bot got another token; created {created_tokens}"


def test_create_bot_creates_exactly_one_bot_for_valid_token(
    created_tokens: list[str],
) -> None:
    token = "987654321:" + "zQ_7-x" * 6
    settings = make_settings(BOT_TOKEN=token)
    expected_tokens = [token]

    bootstrap.create_bot(settings)

    assert created_tokens == expected_tokens, "the bot was not created exactly once"
