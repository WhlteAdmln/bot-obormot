from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config import config
from bot.services.database import db
from bot.handlers.prompt.handler import send_prompt_status

router = Router()


async def is_history_admin(user_id: int) -> bool:
    """Проверяет права Supervisor или администратора."""
    if user_id == config.SUPERVISOR_ID:
        return True

    return user_id in await db.get_admin_ids()


@router.message(Command("history_limit"))
async def cmd_history_limit(
    message: Message,
    state: FSMContext,
    command: CommandObject,
):
    user_id = message.from_user.id
    args = (command.args or "").split()

    is_admin = await is_history_admin(user_id)

    # Без аргументов — показать инструкцию.
    if not args:
        await send_prompt_status(
            message,
            state,
            "Использование:\n"
            "/history — показать текущий лимит\n"
            "/history_limit 20 — установить свой лимит\n"
            "/history_limit ID 100 — установить лимит другому пользователю "
            "(только администратор).",
        )
        return

    # Один аргумент — установить лимит самому себе.
    if len(args) == 1:
        try:
            exchange_limit = int(args[0])
        except ValueError:
            await send_prompt_status(
                message,
                state,
                "⚠️ Укажи целое число.\nПример: /history_limit 20",
            )
            return

        maximum = (
            config.MAX_HISTORY_EXCHANGES
            if is_admin
            else config.DEFAULT_HISTORY_EXCHANGES
        )

        if not 1 <= exchange_limit <= maximum:
            await send_prompt_status(
                message,
                state,
                f"⚠️ Допустимый лимит: от 1 до {maximum}.",
            )
            return

        await db.set_history_limit(user_id, exchange_limit)

        await send_prompt_status(
            message,
            state,
            f"✅ Твой лимит истории установлен: {exchange_limit} полных обменов.",
        )
        return

    # Два аргумента — назначение лимита другому пользователю.
    if len(args) == 2:
        if not is_admin:
            await send_prompt_status(
                message,
                state,
                "⛔ Назначать лимиты другим пользователям могут только администраторы.",
            )
            return

        try:
            target_user_id = int(args[0])
            exchange_limit = int(args[1])
        except ValueError:
            await send_prompt_status(
                message,
                state,
                "⚠️ Укажи корректный ID пользователя и целое число лимита.",
            )
            return

        if target_user_id <= 0:
            await send_prompt_status(
                message,
                state,
                "⚠️ ID пользователя должен быть положительным.",
            )
            return

        if not 1 <= exchange_limit <= config.MAX_HISTORY_EXCHANGES:
            await send_prompt_status(
                message,
                state,
                f"⚠️ Допустимый лимит: от 1 до {config.MAX_HISTORY_EXCHANGES}.",
            )
            return

        await db.set_history_limit(target_user_id, exchange_limit)

        await send_prompt_status(
            message,
            state,
            f"✅ Для пользователя {target_user_id} установлен лимит "
            f"{exchange_limit} полных обменов.",
        )
        return

    await send_prompt_status(
        message,
        state,
        "⚠️ Слишком много аргументов.\n"
        "Пример: /history_limit 20 или /history_limit ID 100.",
    )
