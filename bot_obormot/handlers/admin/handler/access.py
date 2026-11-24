# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Permission checks shared by the administrator commands."""

from aiogram.types import Message

from bot_obormot.services.audit import audit
from bot_obormot.services.database import Database
from bot_obormot.settings import Settings


def is_supervisor(message: Message, settings: Settings) -> bool:
    """Returns True when the message was sent by the configured supervisor."""
    if message.from_user is None:
        return False
    return message.from_user.id == settings.SUPERVISOR_ID


def audit_denied(message: Message) -> None:
    """Record a denied admin command when the sender is known."""
    if message.from_user is not None:
        audit("admin_denied", message.from_user.id, None, "denied")


async def is_admin_or_supervisor(
    user_id: int,
    settings: Settings,
    database: Database,
) -> bool:
    """Check whether the user can manage user bans."""
    if user_id == settings.SUPERVISOR_ID:
        return True
    return user_id in await database.get_admin_ids()
