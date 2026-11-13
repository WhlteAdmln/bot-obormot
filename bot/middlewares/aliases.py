# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Type aliases for the aiogram middleware call signature."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram.types import TelegramObject

MiddlewareData = dict[str, Any]
NextHandler = Callable[[TelegramObject, MiddlewareData], Awaitable[Any]]
