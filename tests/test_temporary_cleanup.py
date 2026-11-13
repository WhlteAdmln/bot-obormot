# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message, Update, User

from bot.fsm.keys import (
    PROMPT_FLOW_KEY,
    PROMPT_STATUS_MESSAGE_KEY,
    UNKNOWN_COMMAND_MESSAGE_KEY,
    UNKNOWN_COMMAND_STATUS_MESSAGE_KEY,
    WELCOME_MESSAGE_KEY,
)
from bot.fsm.states import PromptStates
from bot.middlewares.temporary_messages import TemporaryMessagesCleanupMiddleware

USER_ID = 111111111
CHAT_ID = 111111111


class FakeState:
    """Упрощённая имитация FSMContext."""

    def __init__(self, data=None, current_state=None):
        self.data = dict(data or {})
        self.current_state = current_state

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def get_state(self):
        return self.current_state

    async def set_state(self, state):
        self.current_state = state.state if state else None

    async def clear(self):
        self.data.clear()
        self.current_state = None


def make_message(text="Обычное сообщение"):
    """Создаёт тестовое сообщение aiogram без обращения к Telegram."""

    return Message(
        message_id=100,
        date=datetime.now(UTC),
        chat=Chat(
            id=CHAT_ID,
            type="private",
        ),
        from_user=User(
            id=USER_ID,
            is_bot=False,
            first_name="Test",
        ),
        text=text,
    )


@pytest.fixture
def middleware():
    return TemporaryMessagesCleanupMiddleware()


@pytest.fixture
def handler():
    return AsyncMock(return_value="handled")


@pytest.mark.asyncio
async def test_delete_status_message(
    middleware,
    handler,
    monkeypatch,
):
    """Удаляется временное уведомление после следующего сообщения."""

    event = make_message()
    state = FakeState({PROMPT_STATUS_MESSAGE_KEY: 500})

    delete_mock = AsyncMock()
    monkeypatch.setattr(
        TemporaryMessagesCleanupMiddleware,
        "_delete_message",
        delete_mock,
    )

    result = await middleware(handler, event, {"state": state})

    assert result == "handled"
    delete_mock.assert_awaited_once_with(
        event,
        500,
        "временное уведомление",
    )
    assert state.data[PROMPT_STATUS_MESSAGE_KEY] is None
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_welcome_message(
    middleware,
    handler,
    monkeypatch,
):
    """Удаляется приветствие после следующего сообщения."""

    event = make_message()
    state = FakeState({WELCOME_MESSAGE_KEY: 600})

    delete_mock = AsyncMock()
    monkeypatch.setattr(
        TemporaryMessagesCleanupMiddleware,
        "_delete_message",
        delete_mock,
    )

    result = await middleware(handler, event, {"state": state})

    assert result == "handled"
    delete_mock.assert_awaited_once_with(
        event,
        600,
        "приветствие start",
    )
    assert state.data[WELCOME_MESSAGE_KEY] is None
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_status_and_welcome(
    middleware,
    handler,
    monkeypatch,
):
    """Удаляются оба временных сообщения."""

    event = make_message()
    state = FakeState(
        {
            PROMPT_STATUS_MESSAGE_KEY: 500,
            WELCOME_MESSAGE_KEY: 600,
        }
    )

    delete_mock = AsyncMock()
    monkeypatch.setattr(
        TemporaryMessagesCleanupMiddleware,
        "_delete_message",
        delete_mock,
    )

    await middleware(handler, event, {"state": state})

    assert delete_mock.await_count == 2
    assert delete_mock.await_args_list[0].args == (
        event,
        500,
        "временное уведомление",
    )
    assert delete_mock.await_args_list[1].args == (
        event,
        600,
        "приветствие start",
    )

    assert state.data[PROMPT_STATUS_MESSAGE_KEY] is None
    assert state.data[WELCOME_MESSAGE_KEY] is None


@pytest.mark.asyncio
async def test_command_after_status_is_not_deleted(
    middleware,
    handler,
    monkeypatch,
):
    """Следующая команда не удаляется вместе с временным уведомлением."""

    event = make_message("/help")
    state = FakeState({PROMPT_STATUS_MESSAGE_KEY: 500})

    cleanup_mock = AsyncMock()
    user_message_delete = AsyncMock()

    monkeypatch.setattr(
        TemporaryMessagesCleanupMiddleware,
        "_delete_message",
        cleanup_mock,
    )
    monkeypatch.setattr(
        Message,
        "delete",
        user_message_delete,
    )

    result = await middleware(handler, event, {"state": state})

    assert result == "handled"
    cleanup_mock.assert_awaited_once_with(
        event,
        500,
        "временное уведомление",
    )
    user_message_delete.assert_not_awaited()
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_regular_message_is_not_deleted(
    middleware,
    handler,
    monkeypatch,
):
    """Обычное сообщение не удаляется из-за временного уведомления."""

    event = make_message("Привет!")
    state = FakeState({PROMPT_STATUS_MESSAGE_KEY: 500})

    cleanup_mock = AsyncMock()
    user_message_delete = AsyncMock()

    monkeypatch.setattr(
        TemporaryMessagesCleanupMiddleware,
        "_delete_message",
        cleanup_mock,
    )
    monkeypatch.setattr(
        Message,
        "delete",
        user_message_delete,
    )

    await middleware(handler, event, {"state": state})

    cleanup_mock.assert_awaited_once()
    user_message_delete.assert_not_awaited()
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_messages_are_not_deleted_twice(
    middleware,
    handler,
    monkeypatch,
):
    """После очистки ID повторное удаление не выполняется."""

    event = make_message()
    state = FakeState(
        {
            PROMPT_STATUS_MESSAGE_KEY: 500,
            WELCOME_MESSAGE_KEY: 600,
        }
    )

    delete_mock = AsyncMock()
    monkeypatch.setattr(
        TemporaryMessagesCleanupMiddleware,
        "_delete_message",
        delete_mock,
    )

    await middleware(handler, event, {"state": state})

    assert delete_mock.await_count == 2

    delete_mock.reset_mock()
    handler.reset_mock()

    await middleware(handler, event, {"state": state})

    delete_mock.assert_not_awaited()
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_prompt_flow_messages(
    middleware,
    handler,
    monkeypatch,
):
    """Сообщения просмотра промпта удаляются при следующем сообщении."""

    event = make_message("/health")
    state = FakeState(
        {
            PROMPT_FLOW_KEY: [300, 301],
        }
    )

    delete_mock = AsyncMock()
    monkeypatch.setattr(
        TemporaryMessagesCleanupMiddleware,
        "_delete_message",
        delete_mock,
    )

    await middleware(handler, event, {"state": state})

    assert delete_mock.await_count == 2
    assert delete_mock.await_args_list[0].args == (
        event,
        301,
        "сообщение процесса настройки промпта",
    )
    assert delete_mock.await_args_list[1].args == (
        event,
        300,
        "сообщение процесса настройки промпта",
    )
    assert state.data[PROMPT_FLOW_KEY] == []


@pytest.mark.asyncio
async def test_prompt_flow_is_preserved_while_waiting_for_prompt(
    middleware,
    handler,
    monkeypatch,
):
    """Во время ввода промпта сообщения процесса не удаляются."""

    event = make_message("Новый системный промпт")
    state = FakeState(
        {PROMPT_FLOW_KEY: [300, 301]},
        current_state=PromptStates.waiting_for_prompt.state,
    )

    delete_mock = AsyncMock()
    monkeypatch.setattr(
        TemporaryMessagesCleanupMiddleware,
        "_delete_message",
        delete_mock,
    )

    await middleware(handler, event, {"state": state})

    delete_mock.assert_not_awaited()
    assert state.data[PROMPT_FLOW_KEY] == [300, 301]
    assert await state.get_state() == PromptStates.waiting_for_prompt.state


@pytest.mark.asyncio
async def test_delete_unknown_command_and_response(
    middleware,
    handler,
    monkeypatch,
):
    """Удаляются неизвестная команда и ответ на неё."""

    event = make_message("/unknown")
    state = FakeState(
        {
            UNKNOWN_COMMAND_MESSAGE_KEY: 700,
            UNKNOWN_COMMAND_STATUS_MESSAGE_KEY: 701,
        }
    )

    delete_mock = AsyncMock()
    monkeypatch.setattr(
        TemporaryMessagesCleanupMiddleware,
        "_delete_message",
        delete_mock,
    )

    await middleware(handler, event, {"state": state})

    assert delete_mock.await_count == 2
    assert delete_mock.await_args_list[0].args == (
        event,
        700,
        "неизвестную команду",
    )
    assert delete_mock.await_args_list[1].args == (
        event,
        701,
        "ответ на неизвестную команду",
    )

    assert state.data[UNKNOWN_COMMAND_MESSAGE_KEY] is None
    assert state.data[UNKNOWN_COMMAND_STATUS_MESSAGE_KEY] is None


@pytest.mark.asyncio
async def test_without_fsm_state(
    middleware,
    handler,
    monkeypatch,
):
    """При отсутствии FSM обработчик продолжает работать."""

    event = make_message()

    delete_mock = AsyncMock()
    monkeypatch.setattr(
        TemporaryMessagesCleanupMiddleware,
        "_delete_message",
        delete_mock,
    )

    result = await middleware(handler, event, {})

    assert result == "handled"
    delete_mock.assert_not_awaited()
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_message_event(
    middleware,
    handler,
    monkeypatch,
):
    """События, не являющиеся Message, передаются дальше."""

    event = Update(update_id=1)

    delete_mock = AsyncMock()
    monkeypatch.setattr(
        TemporaryMessagesCleanupMiddleware,
        "_delete_message",
        delete_mock,
    )

    result = await middleware(handler, event, {})

    assert result == "handled"
    delete_mock.assert_not_awaited()
    handler.assert_awaited_once()
