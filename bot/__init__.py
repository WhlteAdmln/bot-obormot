# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Deprecated compatibility package for ``python -m bot.main``.

Systemd units written for bot-obormot 0.1.x start the bot with
``python -m bot.main``. This package keeps them working for one release and is
removed in 0.3.0. Use the ``bot-obormot`` command or ``python -m bot_obormot``.
"""
