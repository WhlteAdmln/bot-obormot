# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Тонкая точка входа; реализация находится в :mod:`bot.app`."""

import asyncio
from contextlib import suppress

from bot.app.bootstrap import main

__all__ = ["main"]


if __name__ == "__main__":
    with suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(main())
