# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Loading of the default system prompt from package resources."""

from importlib.resources import files


def load_default_system_prompt() -> str:
    """Reads the default system prompt file and returns its stripped text."""
    prompt_path = files("bot_obormot").joinpath("prompts", "systemPrompt.md")

    try:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as error:
        msg = f"System prompt file not found: {prompt_path}"
        raise RuntimeError(msg) from error

    if not prompt:
        msg = f"System prompt file is empty: {prompt_path}"
        raise ValueError(msg)

    return prompt
