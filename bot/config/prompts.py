# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Loading of the default system prompt from the prompts directory."""

from bot.config.paths import PROJECT_ROOT


def load_default_system_prompt() -> str:
    """Reads the default system prompt file and returns its stripped text."""
    prompt_path = PROJECT_ROOT / "prompts" / "systemPrompt.md"

    try:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as error:
        msg = f"Файл системного промпта не найден: {prompt_path}"
        raise RuntimeError(msg) from error

    if not prompt:
        msg = f"Файл системного промпта пуст: {prompt_path}"
        raise ValueError(msg)

    return prompt
