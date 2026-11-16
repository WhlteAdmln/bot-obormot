# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Command-line entry point for the bot."""

import asyncio
from contextlib import suppress

from bot.app.bootstrap import main as run_bot


def main() -> None:
    """Run the Telegram bot."""
    with suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(run_bot())
