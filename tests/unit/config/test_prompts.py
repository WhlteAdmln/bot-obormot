# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for default system prompt loading."""

from pathlib import Path

import pytest

from bot_obormot.config import prompts


def test_load_default_system_prompt_reports_missing_file_in_english(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prompts, "files", lambda _: tmp_path)
    prompt_path = tmp_path / "prompts" / "systemPrompt.md"

    with pytest.raises(RuntimeError) as error:
        prompts.load_default_system_prompt()

    assert str(error.value) == f"System prompt file not found: {prompt_path}"


def test_load_default_system_prompt_reports_empty_file_in_english(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prompts, "files", lambda _: tmp_path)
    prompt_path = tmp_path / "prompts" / "systemPrompt.md"
    prompt_path.parent.mkdir()
    prompt_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="System prompt file is empty") as error:
        prompts.load_default_system_prompt()

    assert str(error.value) == f"System prompt file is empty: {prompt_path}"
