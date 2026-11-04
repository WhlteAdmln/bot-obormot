"""Tests for application composition and resource lifecycle."""

import asyncio
import importlib
import sys
import types
from types import SimpleNamespace

import pytest


def _module(name: str, **attributes):
    result = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(result, key, value)
    return result


@pytest.fixture
def router_dependencies(monkeypatch):
    class FakeDispatcher:
        def __init__(self):
            self.middleware_calls = []
            self.routers = []
            self.message = SimpleNamespace(
                middleware=lambda middleware: self.middleware_calls.append(middleware)
            )

        def include_router(self, router):
            self.routers.append(router)

    class FakeAccessMiddleware:
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
        FakeAccessMiddleware,
        FakeCleanupMiddleware,
        router_refs,
        routers_module,
    )
    sys.modules.pop("bot.app.routers", None)


def test_dispatcher_registers_middlewares_and_routers_once_in_original_order(
    router_dependencies,
):
    (
        FakeDispatcher,
        FakeAccessMiddleware,
        FakeCleanupMiddleware,
        router_refs,
        routers_module,
    ) = router_dependencies

    dispatcher = FakeDispatcher()
    configured = routers_module.configure_dispatcher(dispatcher)

    assert configured is dispatcher
    assert len(dispatcher.middleware_calls) == 2
    assert isinstance(dispatcher.middleware_calls[0], FakeAccessMiddleware)
    assert isinstance(dispatcher.middleware_calls[1], FakeCleanupMiddleware)
    assert len(dispatcher.routers) == 4
    assert dispatcher.routers == [
        router_refs["start"],
        router_refs["admin"],
        router_refs["commands"],
        router_refs["chat"],
    ]


def test_periodic_cleanup_uses_existing_policy_and_propagates_cancellation(
    monkeypatch,
):
    calls = []

    class FakeDatabase:
        async def cleanup_old_images(self, **kwargs):
            calls.append(kwargs)
            return {"old_images": 1, "orphan_images": 2, "failed": 0}

    async def stop_after_first_iteration(_delay):
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
def lifecycle_dependencies(monkeypatch):
    calls = []

    class FakeBot:
        def __init__(self):
            async def close_session():
                calls.append("telegram.close")

            self.session = SimpleNamespace(close=close_session)

    class FakeDispatcher:
        async def start_polling(self, bot, **kwargs):
            assert isinstance(bot, FakeBot)
            assert kwargs == {"close_bot_session": False}
            calls.append("polling")
            # Let the just-created background task start before polling returns.
            await asyncio.sleep(0)

    class FakeDatabase:
        async def connect(self):
            calls.append("db.connect")

        async def close(self):
            calls.append("db.close")

    class FakeLLM:
        async def start(self):
            calls.append("llm.start")

        async def close(self):
            calls.append("llm.close")

    async def fake_periodic_cleanup():
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


def _async_call(calls, value):
    calls.append(value)


def test_lifecycle_preserves_startup_polling_and_shutdown_order(
    lifecycle_dependencies,
):
    FakeBot, FakeDispatcher, calls, lifecycle = lifecycle_dependencies

    asyncio.run(lifecycle.run_application(FakeBot(), FakeDispatcher()))

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
    lifecycle_dependencies,
):
    FakeBot, FakeDispatcher, calls, lifecycle = lifecycle_dependencies

    async def fail_connect():
        calls.append("db.connect")
        raise RuntimeError("database unavailable")

    lifecycle.db.connect = fail_connect

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(lifecycle.run_application(FakeBot(), FakeDispatcher()))

    assert calls == [
        "db.connect",
        "llm.close",
        "db.close",
        "telegram.close",
    ]


def test_lifecycle_continues_closing_after_one_cleanup_error(
    lifecycle_dependencies,
):
    FakeBot, FakeDispatcher, calls, lifecycle = lifecycle_dependencies

    async def fail_llm_close():
        calls.append("llm.close")
        raise RuntimeError("LLM close failed")

    lifecycle.llm_client.close = fail_llm_close

    asyncio.run(lifecycle.run_application(FakeBot(), FakeDispatcher()))

    assert calls[-3:] == ["llm.close", "db.close", "telegram.close"]


def test_bootstrap_main_calls_components_in_order(monkeypatch):
    calls = []
    bot_instance = object()
    dispatcher_instance = object()

    monkeypatch.setitem(
        sys.modules,
        "aiogram",
        _module("aiogram", Bot=object, Dispatcher=object),
    )

    async def run_application(bot, dispatcher):
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
    sys.modules.pop("bot.app.bootstrap", None)
    bootstrap = importlib.import_module("bot.app.bootstrap")

    monkeypatch.setattr(bootstrap, "configure_logging", lambda: calls.append("logging"))
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

    assert calls == ["logging", "bot", "dispatcher", "run"]


def test_main_module_is_a_thin_compatible_entrypoint():
    from bot.app.background.image_cleanup import (
        IMAGE_CLEANUP_INTERVAL,
        periodic_image_cleanup,
    )
    from bot.app.bootstrap import main
    import bot.main as main_module

    assert main_module.main is main
    assert main_module.periodic_image_cleanup is periodic_image_cleanup
    assert main_module.IMAGE_CLEANUP_INTERVAL == IMAGE_CLEANUP_INTERVAL
