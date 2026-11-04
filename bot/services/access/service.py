"""Оркестрация проверок доступа."""

from bot.services.access.roles import (
    is_allowlisted,
    is_database_admin,
    is_supervisor,
)


async def user_has_access(
    user_id: int,
    *,
    supervisor_id: int,
    allowed_users: set[int],
    database,
    allow_all: bool = False,
) -> bool:
    """Определяет доступ. Пустой allowlist не открывает доступ автоматически."""

    if is_supervisor(user_id, supervisor_id):
        return True

    blocked_ids = await database.get_blocked_ids()

    if user_id in blocked_ids:
        return False

    admin_ids = await database.get_admin_ids()

    if is_database_admin(user_id, admin_ids):
        return True

    if allow_all:
        return True

    return is_allowlisted(user_id, allowed_users)
