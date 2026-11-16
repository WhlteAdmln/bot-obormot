# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Pure role and access-list checks."""


def is_supervisor(user_id: int, supervisor_id: int) -> bool:
    """Check whether the user matches the supervisor ID."""
    return user_id == supervisor_id


def is_database_admin(user_id: int, admin_ids: set[int]) -> bool:
    """Check whether the user is in the dynamic administrator list."""
    return user_id in admin_ids


def is_allowlisted(user_id: int, allowed_users: set[int]) -> bool:
    """Check whether the user is in the static allowlist."""
    return user_id in allowed_users
