import logging

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from bot.fsm.keys import (
    PROMPT_FLOW_KEY,
    PROMPT_STATUS_MESSAGE_KEY,
    UNKNOWN_COMMAND_MESSAGE_KEY,
    UNKNOWN_COMMAND_STATUS_MESSAGE_KEY,
    WELCOME_MESSAGE_KEY,
)
from bot.fsm.states import PromptStates

logger = logging.getLogger("bot.middlewares.temporary_messages.middleware")


class TemporaryMessagesCleanupMiddleware(BaseMiddleware):
    """Удаляет временные технические сообщения при следующем сообщении пользователя."""

    async def __call__(self, handler, event: TelegramObject, data: dict):
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

        # Во время ввода нового промпта сохраняем сообщения процесса.
        # В остальных случаях очищаем результат /prompt и сообщения настройки.
        prompt_flow_ids = []
        if not waiting_for_prompt:
            prompt_flow_ids = state_data.get(PROMPT_FLOW_KEY, [])

        # Сначала удаляем ID из FSM, чтобы не пытаться удалить их повторно.
        updates = {
            PROMPT_STATUS_MESSAGE_KEY: None,
            WELCOME_MESSAGE_KEY: None,
            UNKNOWN_COMMAND_MESSAGE_KEY: None,
            UNKNOWN_COMMAND_STATUS_MESSAGE_KEY: None,
        }

        if not waiting_for_prompt:
            updates[PROMPT_FLOW_KEY] = []

        await state.update_data(**updates)

        # Удаляем временное уведомление.
        if status_message_id:
            await self._delete_message(
                event,
                status_message_id,
                "временное уведомление",
            )

        # Удаляем приветствие /start.
        if welcome_message_id:
            await self._delete_message(
                event,
                welcome_message_id,
                "приветствие start",
            )

        # Удаляем команду и ответ на неизвестную команду.
        if unknown_command_id:
            await self._delete_message(
                event,
                unknown_command_id,
                "неизвестную команду",
            )

        if unknown_status_id:
            await self._delete_message(
                event,
                unknown_status_id,
                "ответ на неизвестную команду",
            )

        # Удаляем сообщения просмотра промпта или завершённого процесса настройки.
        for message_id in sorted(set(prompt_flow_ids), reverse=True):
            await self._delete_message(
                event,
                message_id,
                "сообщение процесса настройки промпта",
            )

        return await handler(event, data)

    @staticmethod
    async def _delete_message(
        event: Message,
        message_id: int,
        description: str,
    ):
        try:
            await event.bot.delete_message(
                chat_id=event.chat.id,
                message_id=message_id,
            )
        except TelegramAPIError:
            logger.warning(
                "Не удалось удалить %s %s в чате %s",
                description,
                message_id,
                event.chat.id,
                exc_info=True,
            )
