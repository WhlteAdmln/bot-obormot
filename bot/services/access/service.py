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
) -> bool:
    """Определяет доступ, сохраняя исходный приоритет ролей.

    Список администраторов читается из БД до проверки allowlist — так же,
    как это делалось в прежнем AccessMiddleware.
    """

    if is_supervisor(user_id, supervisor_id):
        return True

    admin_ids = await database.get_admin_ids()

    if is_database_admin(user_id, admin_ids):
        return True

    if not allowed_users:
        return True

    return is_allowlisted(user_id, allowed_users)
