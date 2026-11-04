import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.fsm.keys import PROMPT_FLOW_KEY, PROMPT_STATUS_MESSAGE_KEY
from bot.fsm.states import PromptStates
from bot.config import config
from bot.services.database import db

logger = logging.getLogger("bot.handlers.commands")
router = Router()
MAX_SYSTEM_PROMPT_LENGTH = 4000
MAX_DISPLAY_LENGTH = 3500


def format_prompt(prompt: str) -> str:
    """Ограничивает длину промпта при отображении в Telegram."""
    if len(prompt) > MAX_DISPLAY_LENGTH:
        return prompt[:MAX_DISPLAY_LENGTH] + "\n\n... (промпт сокращён при отображении)"

    return prompt


async def track_message(state: FSMContext, message: Message):
    """Запоминает ID сообщения, относящегося к настройке промпта."""
    data = await state.get_data()
    message_ids = data.get(PROMPT_FLOW_KEY, [])

    if message.message_id not in message_ids:
        message_ids.append(message.message_id)

    await state.update_data(**{PROMPT_FLOW_KEY: message_ids})


async def delete_prompt_messages(
    message: Message,
    state: FSMContext,
    extra_message_ids: list[int] | None = None,
):
    """Удаляет сообщения процесса настройки промпта."""
    data = await state.get_data()
    message_ids = set(data.get(PROMPT_FLOW_KEY, []))

    if extra_message_ids:
        message_ids.update(extra_message_ids)

    await state.clear()

    for message_id in sorted(message_ids, reverse=True):
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=message_id,
            )
        except TelegramAPIError:
            logger.warning(
                "Не удалось удалить сообщение %s в чате %s",
                message_id,
                message.chat.id,
                exc_info=True,
            )


async def send_prompt_status(
    message: Message,
    state: FSMContext,
    text: str,
):
    """Отправляет временное уведомление и запоминает его ID."""
    response = await message.answer(text)

    await state.update_data(**{PROMPT_STATUS_MESSAGE_KEY: response.message_id})


async def show_prompt(message: Message, state: FSMContext):
    """Показывает текущий системный промпт."""
    await state.clear()
    await track_message(state, message)

    user_id = message.from_user.id
    user_prompt = await db.get_user_system_prompt(user_id)
    current_prompt = await db.get_system_prompt(user_id)

    source = "👤 Персональный" if user_prompt is not None else "📄 Стандартный"

    response = await message.answer(
        "Текущий системный промпт\n"
        f"Источник: {source}\n\n"
        f"{format_prompt(current_prompt)}\n\n"
        "Изменить:\n"
        "/prompt_set\n\n"
        "Сбросить персональный промпт:\n"
        "/prompt_reset"
    )

    await track_message(state, response)


@router.message(Command("prompt"))
async def cmd_prompt(message: Message, state: FSMContext):
    await show_prompt(message, state)


@router.message(Command("prompt_set"))
async def cmd_prompt_set(message: Message, state: FSMContext):
    await track_message(state, message)
    await state.set_state(PromptStates.waiting_for_prompt)

    response = await message.answer(
        "✍️ Отправь следующим сообщением новый системный промпт.\n\n"
        f"Максимальная длина — {MAX_SYSTEM_PROMPT_LENGTH} символов.\n"
        "Для отмены используй /cancel."
    )

    await track_message(state, response)


@router.message(
    PromptStates.waiting_for_prompt,
    F.text,
    ~F.text.startswith("/"),
)
async def save_prompt(message: Message, state: FSMContext):
    prompt = message.text.strip()

    if not prompt:
        await track_message(state, message)
        await send_prompt_status(
            message,
            state,
            "Промпт не может быть пустым. Попробуй ещё раз.",
        )
        return

    if len(prompt) > MAX_SYSTEM_PROMPT_LENGTH:
        await track_message(state, message)
        await send_prompt_status(
            message,
            state,
            f"Промпт слишком длинный. Максимум {MAX_SYSTEM_PROMPT_LENGTH} символов.",
        )
        return

    await db.set_system_prompt(message.from_user.id, prompt)

    await delete_prompt_messages(
        message,
        state,
        extra_message_ids=[message.message_id],
    )

    await send_prompt_status(
        message,
        state,
        "✅ Персональный системный промпт сохранён.\n\n"
        "Теперь он используется только в твоём чате.",
    )


async def reset_prompt(message: Message, state: FSMContext):
    """Сбрасывает персональный промпт и очищает технические сообщения."""
    user_id = message.from_user.id
    user_prompt = await db.get_user_system_prompt(user_id)

    if user_prompt is not None:
        await db.delete_system_prompt(user_id)

    await delete_prompt_messages(
        message,
        state,
        extra_message_ids=[message.message_id],
    )

    if user_prompt is None:
        await send_prompt_status(
            message,
            state,
            "ℹ️ У тебя уже используется стандартный системный промпт.",
        )
        return

    await send_prompt_status(
        message,
        state,
        "🔄 Персональный системный промпт удалён.\n"
        "Теперь используется стандартный промпт.",
    )


@router.message(Command("prompt_reset"))
async def cmd_prompt_reset(message: Message, state: FSMContext):
    await reset_prompt(message, state)


@router.message(Command("cancel"), PromptStates.waiting_for_prompt)
async def cmd_cancel(message: Message, state: FSMContext):
    await delete_prompt_messages(
        message,
        state,
        extra_message_ids=[message.message_id],
    )

    await send_prompt_status(
        message,
        state,
        "❎ Ввод системного промпта отменён.",
    )
