# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Deprecated entry point; forwards to ``bot-obormot run``."""

import sys

from bot_obormot.cli import main as cli_main

DEPRECATION_MESSAGE = (
    "DEPRECATED: 'python -m bot.main' will be removed in bot-obormot 0.3.0. "
    "Use 'bot-obormot run' or run 'bot-obormot service install --force'."
)


def main() -> int:
    """Print the deprecation line and run the bot."""
    sys.stderr.write(f"{DEPRECATION_MESSAGE}\n")
    return cli_main(["run"])


if __name__ == "__main__":
    sys.exit(main())
