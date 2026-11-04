"""Чистые проверки ролей и списков доступа."""


def is_supervisor(user_id: int, supervisor_id: int) -> bool:
    """Проверяет, совпадает ли пользователь с главным администратором."""

    return user_id == supervisor_id


def is_database_admin(user_id: int, admin_ids: set[int]) -> bool:
    """Проверяет наличие пользователя в динамическом списке администраторов."""

    return user_id in admin_ids


def is_allowlisted(user_id: int, allowed_users: set[int]) -> bool:
    """Проверяет наличие пользователя в статическом allowlist."""

    return user_id in allowed_users
