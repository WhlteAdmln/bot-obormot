# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Middleware that removes temporary service messages of the bot."""

import logging
from typing import TYPE_CHECKING, Any, cast

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message, TelegramObject

from bot_obormot.fsm.keys import (
    PROMPT_FLOW_KEY,
    PROMPT_STATUS_MESSAGE_KEY,
    UNKNOWN_COMMAND_MESSAGE_KEY,
    UNKNOWN_COMMAND_STATUS_MESSAGE_KEY,
    WELCOME_MESSAGE_KEY,
)
from bot_obormot.fsm.states import PromptStates
from bot_obormot.middlewares.aliases import MiddlewareData, NextHandler

if TYPE_CHECKING:
    from aiogram import Bot
    from aiogram.fsm.context import FSMContext

logger = logging.getLogger("bot_obormot.middlewares.temporary_messages.middleware")


class TemporaryMessagesCleanupMiddleware(BaseMiddleware):
    """Delete temporary service messages when the user sends another message."""

    async def __call__(
        self,
        handler: NextHandler,
        event: TelegramObject,
        data: MiddlewareData,
    ) -> object:
        """Deletes pending temporary messages before the next handler runs."""
        if not isinstance(event, Message):
            return await handler(event, data)

        state: FSMContext | None = data.get("state")

        if state is None:
            return await handler(event, data)

        state_data = await state.get_data()

        status_message_id = state_data.get(PROMPT_STATUS_MESSAGE_KEY)
        welcome_message_id = state_data.get(WELCOME_MESSAGE_KEY)
        unknown_command_id = state_data.get(UNKNOWN_COMMAND_MESSAGE_KEY)
        unknown_status_id = state_data.get(UNKNOWN_COMMAND_STATUS_MESSAGE_KEY)

        waiting_for_prompt = (
            await state.get_state() == PromptStates.waiting_for_prompt.state
        )

        # Preserve process messages while the user enters a new prompt.
        # Otherwise, clear the /prompt result and setup messages.
        prompt_flow_ids: list[int] = []
        if not waiting_for_prompt:
            prompt_flow_ids = state_data.get(PROMPT_FLOW_KEY, [])

        # Remove IDs from FSM first to avoid attempting to delete them again.
        updates: dict[str, Any] = {
            PROMPT_STATUS_MESSAGE_KEY: None,
            WELCOME_MESSAGE_KEY: None,
            UNKNOWN_COMMAND_MESSAGE_KEY: None,
            UNKNOWN_COMMAND_STATUS_MESSAGE_KEY: None,
        }

        if not waiting_for_prompt:
            updates[PROMPT_FLOW_KEY] = []

        await state.update_data(**updates)

        # Delete the temporary notification.
        if status_message_id:
            await self._delete_message(
                event,
                status_message_id,
                "temporary notification",
            )

        # Delete the /start welcome message.
        if welcome_message_id:
            await self._delete_message(
                event,
                welcome_message_id,
                "start welcome message",
            )

        # Delete the unknown command and its response.
        if unknown_command_id:
            await self._delete_message(
                event,
                unknown_command_id,
                "unknown command",
            )

        if unknown_status_id:
            await self._delete_message(
                event,
                unknown_status_id,
                "unknown command response",
            )

        # Delete prompt viewing messages or messages from a completed setup flow.
        for message_id in sorted(set(prompt_flow_ids), reverse=True):
            await self._delete_message(
                event,
                message_id,
                "prompt setup flow message",
            )

        return await handler(event, data)

    @staticmethod
    async def _delete_message(
        event: Message,
        message_id: int,
        description: str,
    ) -> None:
        try:
            bot = cast("Bot", event.bot)
            await bot.delete_message(
                chat_id=event.chat.id,
                message_id=message_id,
            )
        except TelegramAPIError:
            logger.warning(
                "Failed to delete %s %s in chat %s",
                description,
                message_id,
                event.chat.id,
                exc_info=True,
            )
