# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for temporary_messages middleware."""

from collections.abc import AsyncIterator, Mapping

import pytest
import pytest_asyncio
from aiogram import Bot
from aiogram.methods import DeleteMessage
from aiogram.types import Message, Update

from bot_obormot.fsm.keys import (
    PROMPT_FLOW_KEY,
    PROMPT_STATUS_MESSAGE_KEY,
    UNKNOWN_COMMAND_MESSAGE_KEY,
    UNKNOWN_COMMAND_STATUS_MESSAGE_KEY,
    WELCOME_MESSAGE_KEY,
)
from bot_obormot.fsm.states import PromptStates
from bot_obormot.middlewares.temporary_messages import (
    TemporaryMessagesCleanupMiddleware,
)
from tests.support.fsm import FakeFSMContext
from tests.support.middleware_handler import RecordingHandler
from tests.support.settings import make_settings
from tests.support.telegram import FakeTelegramSession, deleted_messages, make_message


@pytest_asyncio.fixture(name="telegram")
async def fixture_telegram() -> AsyncIterator[tuple[Bot, FakeTelegramSession]]:
    """Create a bot whose fake Telegram session accepts message deletions."""
    session = FakeTelegramSession({DeleteMessage: True})
    bot = Bot(token=make_settings().BOT_TOKEN, session=session)
    try:
        yield bot, session
    finally:
        await bot.session.close()


def _message(bot: Bot, text: str, chat_id: int = 318264507) -> Message:
    return make_message(
        message_id=946, chat_id=chat_id, user_id=chat_id, text=text
    ).as_(bot)


async def _run(
    bot: Bot,
    state_data: Mapping[str, object],
    text: str = "Как настроение?",
) -> FakeFSMContext:
    state = FakeFSMContext(state_data)
    await TemporaryMessagesCleanupMiddleware()(
        RecordingHandler(), _message(bot, text), {"state": state}
    )
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state_data", "text", "expected_ids"),
    [
        pytest.param({PROMPT_STATUS_MESSAGE_KEY: 500}, "Привет!", [500], id="status"),
        pytest.param(
            {WELCOME_MESSAGE_KEY: 613}, "Расскажи анекдот", [613], id="welcome"
        ),
        pytest.param(
            {PROMPT_STATUS_MESSAGE_KEY: 517, WELCOME_MESSAGE_KEY: 604},
            "Что нового?",
            [517, 604],
            id="status-and-welcome",
        ),
        pytest.param(
            {UNKNOWN_COMMAND_MESSAGE_KEY: 702, UNKNOWN_COMMAND_STATUS_MESSAGE_KEY: 709},
            "/unknown",
            [702, 709],
            id="unknown-command",
        ),
        pytest.param(
            {PROMPT_FLOW_KEY: [311, 340]}, "/health", [340, 311], id="prompt-flow"
        ),
        pytest.param(
            {PROMPT_STATUS_MESSAGE_KEY: 528}, "/help", [528], id="next-command"
        ),
    ],
)
async def test_deletes_pending_temporary_messages(
    telegram: tuple[Bot, FakeTelegramSession],
    state_data: dict[str, object],
    text: str,
    expected_ids: list[int],
) -> None:
    bot, session = telegram

    await _run(bot, state_data, text)

    deleted_ids = [message_id for _, message_id in deleted_messages(session)]
    assert deleted_ids == expected_ids, "wrong temporary messages were deleted"


@pytest.mark.asyncio
async def test_deletes_temporary_messages_in_the_chat_of_the_event(
    telegram: tuple[Bot, FakeTelegramSession],
) -> None:
    bot, session = telegram
    chat_id = 570213884
    state = FakeFSMContext({WELCOME_MESSAGE_KEY: 431})

    await TemporaryMessagesCleanupMiddleware()(
        RecordingHandler(), _message(bot, "Доброе утро", chat_id), {"state": state}
    )

    expected = [(chat_id, 431)]
    assert deleted_messages(session) == expected, "message deleted in another chat"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state_data", "key", "expected_value"),
    [
        (
            {PROMPT_STATUS_MESSAGE_KEY: 822},
            PROMPT_STATUS_MESSAGE_KEY,
            None,
        ),
        ({WELCOME_MESSAGE_KEY: 659}, WELCOME_MESSAGE_KEY, None),
        (
            {UNKNOWN_COMMAND_MESSAGE_KEY: 733},
            UNKNOWN_COMMAND_MESSAGE_KEY,
            None,
        ),
        (
            {UNKNOWN_COMMAND_STATUS_MESSAGE_KEY: 734},
            UNKNOWN_COMMAND_STATUS_MESSAGE_KEY,
            None,
        ),
        ({PROMPT_FLOW_KEY: [377, 389]}, PROMPT_FLOW_KEY, []),
    ],
)
async def test_clears_pending_message_ids_from_state(
    telegram: tuple[Bot, FakeTelegramSession],
    state_data: dict[str, object],
    key: str,
    expected_value: object,
) -> None:
    bot, _ = telegram

    state = await _run(bot, state_data)

    assert state.data[key] == expected_value, f"{key} was not cleared"


@pytest.mark.asyncio
async def test_returns_the_handler_result(
    telegram: tuple[Bot, FakeTelegramSession],
) -> None:
    bot, _ = telegram
    expected_result = "ответ обработчика"
    handler = RecordingHandler(expected_result)
    state = FakeFSMContext({PROMPT_STATUS_MESSAGE_KEY: 145})

    result = await TemporaryMessagesCleanupMiddleware()(
        handler, _message(bot, "Сколько времени?"), {"state": state}
    )

    assert result == expected_result, "middleware lost the handler result"


@pytest.mark.asyncio
async def test_passes_the_message_to_the_handler(
    telegram: tuple[Bot, FakeTelegramSession],
) -> None:
    bot, _ = telegram
    handler = RecordingHandler()
    message = _message(bot, "Что посмотреть вечером?")
    state = FakeFSMContext({WELCOME_MESSAGE_KEY: 268})

    await TemporaryMessagesCleanupMiddleware()(handler, message, {"state": state})

    expected_events = [message]
    assert handler.events == expected_events, "handler did not get the message"


@pytest.mark.asyncio
async def test_does_not_delete_messages_twice(
    telegram: tuple[Bot, FakeTelegramSession],
) -> None:
    bot, session = telegram
    middleware = TemporaryMessagesCleanupMiddleware()
    state = FakeFSMContext({PROMPT_STATUS_MESSAGE_KEY: 504, WELCOME_MESSAGE_KEY: 691})
    message = _message(bot, "Ещё вопрос")
    await middleware(RecordingHandler(), message, {"state": state})
    deleted_before = len(deleted_messages(session))

    await middleware(RecordingHandler(), message, {"state": state})

    expected_empty: list[tuple[int | str, int]] = []
    assert deleted_messages(session)[deleted_before:] == expected_empty, (
        "messages were deleted again"
    )


@pytest.mark.asyncio
async def test_keeps_prompt_flow_messages_while_waiting_for_prompt(
    telegram: tuple[Bot, FakeTelegramSession],
) -> None:
    bot, session = telegram
    state = FakeFSMContext(
        {PROMPT_FLOW_KEY: [302, 307]},
        current_state=PromptStates.waiting_for_prompt.state,
    )

    await TemporaryMessagesCleanupMiddleware()(
        RecordingHandler(), _message(bot, "Новый системный промпт"), {"state": state}
    )

    expected_empty: list[tuple[int | str, int]] = []
    assert deleted_messages(session) == expected_empty, "prompt flow was deleted"


@pytest.mark.asyncio
async def test_keeps_prompt_flow_ids_while_waiting_for_prompt(
    telegram: tuple[Bot, FakeTelegramSession],
) -> None:
    bot, _ = telegram
    flow_ids = [315, 326]
    state = FakeFSMContext(
        {PROMPT_FLOW_KEY: flow_ids},
        current_state=PromptStates.waiting_for_prompt.state,
    )

    await TemporaryMessagesCleanupMiddleware()(
        RecordingHandler(), _message(bot, "Будь вежливым"), {"state": state}
    )

    assert state.data[PROMPT_FLOW_KEY] == flow_ids, "prompt flow IDs were cleared"


@pytest.mark.asyncio
async def test_keeps_the_waiting_for_prompt_state(
    telegram: tuple[Bot, FakeTelegramSession],
) -> None:
    bot, _ = telegram
    expected_state = PromptStates.waiting_for_prompt.state
    state = FakeFSMContext({PROMPT_FLOW_KEY: [351]}, current_state=expected_state)

    await TemporaryMessagesCleanupMiddleware()(
        RecordingHandler(), _message(bot, "Отвечай кратко"), {"state": state}
    )

    assert await state.get_state() == expected_state, "FSM state was changed"


@pytest.mark.asyncio
async def test_passes_a_message_without_fsm_state_to_the_handler(
    telegram: tuple[Bot, FakeTelegramSession],
) -> None:
    bot, _ = telegram
    expected_result = "без состояния"

    result = await TemporaryMessagesCleanupMiddleware()(
        RecordingHandler(expected_result), _message(bot, "Где мой ответ?"), {}
    )

    assert result == expected_result, "message without FSM state was not handled"


@pytest.mark.asyncio
async def test_deletes_nothing_without_fsm_state(
    telegram: tuple[Bot, FakeTelegramSession],
) -> None:
    bot, session = telegram

    await TemporaryMessagesCleanupMiddleware()(
        RecordingHandler(), _message(bot, "Тут кто-нибудь есть?"), {}
    )

    expected_empty: list[tuple[int | str, int]] = []
    assert deleted_messages(session) == expected_empty, "messages were deleted"


@pytest.mark.asyncio
async def test_passes_a_non_message_event_to_the_handler() -> None:
    event = Update(update_id=7319)
    handler = RecordingHandler()

    await TemporaryMessagesCleanupMiddleware()(handler, event, {})

    expected_events = [event]
    assert handler.events == expected_events, "non-message event was not passed on"


@pytest.mark.asyncio
async def test_reraises_the_handler_error(
    telegram: tuple[Bot, FakeTelegramSession],
) -> None:
    bot, _ = telegram
    handler = RecordingHandler(error=RuntimeError("обработчик упал"))
    state = FakeFSMContext({PROMPT_STATUS_MESSAGE_KEY: 841})
    error_text = "обработчик упал"

    with pytest.raises(RuntimeError) as excinfo:
        await TemporaryMessagesCleanupMiddleware()(
            handler, _message(bot, "Сломай всё"), {"state": state}
        )

    assert str(excinfo.value) == error_text, "handler error was not re-raised"


@pytest.mark.asyncio
async def test_deletes_temporary_messages_before_a_failing_handler(
    telegram: tuple[Bot, FakeTelegramSession],
) -> None:
    bot, session = telegram
    handler = RecordingHandler(error=RuntimeError("handler failed"))
    state = FakeFSMContext({PROMPT_STATUS_MESSAGE_KEY: 800})

    with pytest.raises(RuntimeError, match="handler failed"):
        await TemporaryMessagesCleanupMiddleware()(
            handler, _message(bot, "Ещё раз"), {"state": state}
        )

    deleted_ids = [message_id for _, message_id in deleted_messages(session)]
    expected_ids = [800]
    assert deleted_ids == expected_ids, "message was not deleted before the error"


@pytest.mark.asyncio
async def test_clears_state_before_a_failing_handler(
    telegram: tuple[Bot, FakeTelegramSession],
) -> None:
    bot, _ = telegram
    handler = RecordingHandler(error=RuntimeError("handler failed"))
    state = FakeFSMContext({PROMPT_STATUS_MESSAGE_KEY: 812})

    with pytest.raises(RuntimeError, match="handler failed"):
        await TemporaryMessagesCleanupMiddleware()(
            handler, _message(bot, "Попробуй снова"), {"state": state}
        )

    assert state.data[PROMPT_STATUS_MESSAGE_KEY] is None, "state was not cleared"
