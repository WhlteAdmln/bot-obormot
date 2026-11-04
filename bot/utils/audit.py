"""Журнал аудита административных действий."""

import logging

audit_logger = logging.getLogger("bot.audit")


def audit(
    action: str,
    actor_id: int,
    target_id: int | None = None,
    result: str = "ok",
) -> None:
    """Пишет одну понятную строку о действии администратора."""
    audit_logger.info(
        "AUDIT action=%s actor=%s target=%s result=%s",
        action,
        actor_id,
        target_id,
        result,
    )
