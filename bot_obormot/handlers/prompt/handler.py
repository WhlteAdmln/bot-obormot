# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Handlers for viewing, changing and resetting the personal system prompt."""

import logging
from typing import TYPE_CHECKING, Any, cast

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot_obormot.fsm.keys import PROMPT_FLOW_KEY, PROMPT_STATUS_MESSAGE_KEY
from bot_obormot.fsm.states import PromptStates
from bot_obormot.handlers.prompt import texts
from bot_obormot.services.database import Database

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger("bot_obormot.handlers.prompt.handler")
router = Router()
MAX_SYSTEM_PROMPT_LENGTH = 4000
MAX_DISPLAY_LENGTH = 3500


def format_prompt(prompt: str) -> str:
    """Limit the displayed prompt length for Telegram."""
    if len(prompt) > MAX_DISPLAY_LENGTH:
        return prompt[:MAX_DISPLAY_LENGTH] + texts.PROMPT_TRUNCATION_SUFFIX

    return prompt


async def track_message(state: FSMContext, message: Message) -> None:
    """Track the ID of a message related to prompt configuration."""
    data = await state.get_data()
    message_ids = data.get(PROMPT_FLOW_KEY, [])

    if message.message_id not in message_ids:
        message_ids.append(message.message_id)

    await state.update_data(**{PROMPT_FLOW_KEY: message_ids})


async def delete_prompt_messages(
    message: Message,
    state: FSMContext,
    extra_message_ids: list[int] | None = None,
) -> None:
    """Delete messages associated with the prompt setup flow."""
    data = await state.get_data()
    message_ids = set(data.get(PROMPT_FLOW_KEY, []))

    if extra_message_ids:
        message_ids.update(extra_message_ids)

    await state.clear()

    bot = cast("Bot", message.bot)

    for message_id in sorted(message_ids, reverse=True):
        try:
            await bot.delete_message(
                chat_id=message.chat.id,
                message_id=message_id,
            )
        except TelegramAPIError:
            logger.warning(
                "Could not delete message %s in chat %s",
                message_id,
                message.chat.id,
                exc_info=True,
            )


async def send_prompt_status(
    message: Message,
    state: FSMContext,
    text: str,
) -> None:
    """Send a temporary notification and store its ID."""
    response = await message.answer(text)

    data: dict[str, Any] = {PROMPT_STATUS_MESSAGE_KEY: response.message_id}
    await state.update_data(**data)


async def show_prompt(message: Message, state: FSMContext, database: Database) -> None:
    """Display the current system prompt."""
    await state.clear()
    await track_message(state, message)

    if message.from_user is None:
        return

    user_id = message.from_user.id
    user_prompt = await database.get_user_system_prompt(user_id)
    current_prompt = await database.get_system_prompt(user_id)

    source = (
        texts.PERSONAL_PROMPT_SOURCE
        if user_prompt is not None
        else texts.DEFAULT_PROMPT_SOURCE
    )

    response = await message.answer(
        texts.PROMPT_DISPLAY_TEMPLATE.format(
            source=source,
            prompt=format_prompt(current_prompt),
        )
    )

    await track_message(state, response)


@router.message(Command("prompt"))
async def cmd_prompt(message: Message, state: FSMContext, database: Database) -> None:
    """Shows the current system prompt."""
    await show_prompt(message, state, database)


@router.message(Command("prompt_set"))
async def cmd_prompt_set(message: Message, state: FSMContext) -> None:
    """Asks the user to send a new system prompt."""
    await track_message(state, message)
    await state.set_state(PromptStates.waiting_for_prompt)

    response = await message.answer(
        texts.PROMPT_INPUT_TEMPLATE.format(max_length=MAX_SYSTEM_PROMPT_LENGTH)
    )

    await track_message(state, response)


@router.message(
    PromptStates.waiting_for_prompt,
    F.text,
    ~F.text.startswith("/"),
)
async def save_prompt(message: Message, state: FSMContext, database: Database) -> None:
    """Validates and saves the personal system prompt sent by the user."""
    if message.text is None or message.from_user is None:
        return

    prompt = message.text.strip()

    if not prompt:
        await track_message(state, message)
        await send_prompt_status(
            message,
            state,
            texts.PROMPT_EMPTY_ERROR,
        )
        return

    if len(prompt) > MAX_SYSTEM_PROMPT_LENGTH:
        await track_message(state, message)
        await send_prompt_status(
            message,
            state,
            texts.PROMPT_TOO_LONG_ERROR.format(max_length=MAX_SYSTEM_PROMPT_LENGTH),
        )
        return

    await database.set_system_prompt(message.from_user.id, prompt)

    await delete_prompt_messages(
        message,
        state,
        extra_message_ids=[message.message_id],
    )

    await send_prompt_status(message, state, texts.PROMPT_SAVED)


async def reset_prompt(message: Message, state: FSMContext, database: Database) -> None:
    """Reset the personal prompt and clear technical messages."""
    if message.from_user is None:
        return

    user_id = message.from_user.id
    user_prompt = await database.get_user_system_prompt(user_id)

    if user_prompt is not None:
        await database.delete_system_prompt(user_id)

    await delete_prompt_messages(
        message,
        state,
        extra_message_ids=[message.message_id],
    )

    if user_prompt is None:
        await send_prompt_status(
            message,
            state,
            texts.PROMPT_RESET_ALREADY_DEFAULT,
        )
        return

    await send_prompt_status(
        message,
        state,
        texts.PROMPT_RESET_DONE,
    )


@router.message(Command("prompt_reset"))
async def cmd_prompt_reset(
    message: Message, state: FSMContext, database: Database
) -> None:
    """Resets the personal system prompt to the default one."""
    await reset_prompt(message, state, database)


@router.message(Command("cancel"), PromptStates.waiting_for_prompt)
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Cancels the system prompt input."""
    await delete_prompt_messages(
        message,
        state,
        extra_message_ids=[message.message_id],
    )

    await send_prompt_status(
        message,
        state,
        texts.PROMPT_CANCELLED,
    )
