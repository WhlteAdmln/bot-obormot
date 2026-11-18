# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Validation of the Telegram bot token format."""

import re

BOT_TOKEN_PATTERN = re.compile(r"\d{5,}:[A-Za-z0-9_-]{30,}")


def is_valid_bot_token(token: str) -> bool:
    """Return whether the value looks like a Telegram bot token."""
    return BOT_TOKEN_PATTERN.fullmatch(token) is not None
