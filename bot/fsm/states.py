"""Finite-state machine states used by the bot handlers."""

from aiogram.fsm.state import State, StatesGroup


class PromptStates(StatesGroup):
    waiting_for_prompt = State()
