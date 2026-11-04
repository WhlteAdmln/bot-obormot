import asyncio
import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.config import config
from bot.services.database import db
from bot.services.llm import llm_client


router = Router()
logger = logging.getLogger("bot.handlers.admin")


def is_supervisor(message: Message) -> bool:
    return (
        message.from_user is not None and message.from_user.id == config.SUPERVISOR_ID
    )


async def check_telegram(message: Message) -> tuple[bool, str]:
    """Проверяет доступность Telegram Bot API."""

    try:
        await message.bot.get_me()
        return True, "Доступен"

    except Exception:
        logger.exception("Telegram health check failed")
        return False, "Недоступен"


async def check_database() -> tuple[bool, str]:
    """Проверяет доступность SQLite."""

    try:
        await db.health_check()
        return True, "Подключена"

    except Exception:
        logger.exception("Database health check failed")
        return False, "Ошибка подключения"


@router.message(Command("health"))
async def cmd_health(message: Message):
    """Показывает состояние основных компонентов бота."""

    if not message.from_user:
        return

    user_id = message.from_user.id

    # Supervisor всегда имеет доступ.
    # Остальные администраторы проверяются по SQLite.
    if not is_supervisor(message):
        try:
            admin_ids = await db.get_admin_ids()

        except Exception:
            logger.exception("Could not verify admin permissions for /health")
            await message.answer("⚠️ Не удалось проверить права администратора.")
            return

        if user_id not in admin_ids:
            await message.answer("⛔ Доступ запрещён.")
            return

    status_message = await message.answer("🔎 Проверяю состояние компонентов...")

    # Выполняем проверки параллельно.
    telegram_result, database_result, llm_result = await asyncio.gather(
        check_telegram(message),
        check_database(),
        llm_client.health_check(),
    )

    def format_status(
        name: str,
        result: tuple[bool, str],
    ) -> str:
        is_ok, detail = result
        icon = "🟢" if is_ok else "🔴"

        return f"{icon} {name}: {detail}"

    report = (
        "🩺 <b>Состояние бота</b>\n\n"
        f"{format_status('Telegram API', telegram_result)}\n"
        f"{format_status('База данных', database_result)}\n"
        f"{format_status('Инференс', llm_result)}"
    )

    await status_message.edit_text(
        report,
        parse_mode="HTML",
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_supervisor(message):
        await message.answer("⛔ Доступ запрещён.")
        return

    admin_ids = await db.get_admin_ids()

    await message.answer(
        "🛠 Панель управления\n\n"
        f"👑 Supervisor ID: {config.SUPERVISOR_ID}\n"
        f"👥 Обычных администраторов: {len(admin_ids)}\n"
        f"🔐 Пользователей в allowlist: {len(config.ALLOWED_USERS)}\n\n"
        "Команды управления:\n"
        "/admins — список администраторов\n"
        "/admin_add ID — добавить администратора\n"
        "/admin_remove ID — удалить администратора"
    )


@router.message(Command("admins"))
async def cmd_admins(message: Message):
    if not is_supervisor(message):
        await message.answer("⛔ Доступ запрещён.")
        return

    admin_ids = sorted(await db.get_admin_ids())

    text = f"👥 Список администраторов\n\n👑 Supervisor: {config.SUPERVISOR_ID}\n"

    if admin_ids:
        text += "\nОбычные администраторы:\n"
        text += "\n".join(f"• {user_id}" for user_id in admin_ids)
    else:
        text += "\nОбычных администраторов пока нет."

    await message.answer(text)


@router.message(Command("admin_add"))
async def cmd_admin_add(
    message: Message,
    command: CommandObject,
):
    if not is_supervisor(message):
        await message.answer("⛔ Доступ запрещён.")
        return

    argument = (command.args or "").strip()

    if not argument:
        await message.answer(
            "Укажи Telegram ID пользователя.\nПример: /admin_add 123456789"
        )
        return

    try:
        user_id = int(argument)
    except ValueError:
        await message.answer("⛔ Telegram ID должен быть целым числом.")
        return

    if user_id <= 0:
        await message.answer("⛔ Telegram ID должен быть положительным числом.")
        return

    if user_id == config.SUPERVISOR_ID:
        await message.answer("ℹ️ Этот пользователь уже является Supervisor.")
        return

    added = await db.add_admin(user_id)

    if added:
        await message.answer(
            f"✅ Пользователь {user_id} добавлен в список администраторов."
        )
    else:
        await message.answer(f"ℹ️ Пользователь {user_id} уже является администратором.")


@router.message(Command("admin_remove"))
async def cmd_admin_remove(
    message: Message,
    command: CommandObject,
):
    if not is_supervisor(message):
        await message.answer("⛔ Доступ запрещён.")
        return

    argument = (command.args or "").strip()

    if not argument:
        await message.answer(
            "Укажи Telegram ID пользователя.\nПример: /admin_remove 123456789"
        )
        return

    try:
        user_id = int(argument)
    except ValueError:
        await message.answer("⛔ Telegram ID должен быть целым числом.")
        return

    if user_id <= 0:
        await message.answer("⛔ Telegram ID должен быть положительным числом.")
        return

    if user_id == config.SUPERVISOR_ID:
        await message.answer("⛔ Нельзя удалить Supervisor.")
        return

    removed = await db.remove_admin(user_id)

    if removed:
        await message.answer(
            f"✅ Пользователь {user_id} удалён из списка администраторов."
        )
    else:
        await message.answer(
            f"ℹ️ Пользователь {user_id} не найден среди администраторов."
        )
