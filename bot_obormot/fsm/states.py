# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Finite-state machine states used by the bot handlers."""

from aiogram.fsm.state import State, StatesGroup


class PromptStates(StatesGroup):
    """States of the system prompt editing dialog."""

    waiting_for_prompt = State()
