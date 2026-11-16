# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Audit logging for administrative actions."""

import logging

audit_logger = logging.getLogger("bot.audit")


def audit(
    action: str,
    actor_id: int,
    target_id: int | None = None,
    result: str = "ok",
) -> None:
    """Log one structured line describing an administrative action."""
    audit_logger.info(
        "AUDIT action=%s actor=%s target=%s result=%s",
        action,
        actor_id,
        target_id,
        result,
    )
