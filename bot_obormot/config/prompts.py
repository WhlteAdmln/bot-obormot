# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Loading of the default system prompt from package resources or a file."""

from importlib.resources import files
from pathlib import Path


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


def load_system_prompt_file(path: Path) -> str:
    """Reads an administrator's system prompt file and returns its stripped text.

    Raises ``ValueError`` with a short reason when the file cannot be used.
    """
    try:
        prompt = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as error:
        msg = f"cannot read {path}: {error}"
        raise ValueError(msg) from error

    if not prompt:
        msg = f"{path} is empty"
        raise ValueError(msg)

    return prompt
