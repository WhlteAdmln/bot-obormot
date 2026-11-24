# Copyright (c) 2026 Nikolai Zelensky
"""Tests for the Telegram commands documentation check."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.docs_checks.telegram_commands import check_telegram_commands

if TYPE_CHECKING:
    from pathlib import Path


def _write_files(root: Path, guide: str) -> None:
    (root / "bot_obormot").mkdir()
    (root / "docs").mkdir()
    (root / "bot_obormot" / "handler.py").write_text(
        'router.message(Command("start"))\nrouter.message(Command("history_limit"))\n',
        encoding="utf-8",
    )
    (root / "docs" / "commands.md").write_text(guide, encoding="utf-8")


def test_accepts_a_guide_that_names_every_command(tmp_path: Path) -> None:
    _write_files(tmp_path, "`/start`\n`/history_limit N`\n")
    expected_empty: list[str] = []

    errors = check_telegram_commands(tmp_path)

    assert errors == expected_empty, "a complete guide must pass"


def test_reports_a_command_missing_from_the_guide(tmp_path: Path) -> None:
    _write_files(tmp_path, "`/start`\n")
    expected = ["docs/commands.md: missing commands: /history_limit"]

    errors = check_telegram_commands(tmp_path)

    assert errors == expected, "a command missing from the guide must be reported"


def test_reports_a_missing_commands_guide(tmp_path: Path) -> None:
    expected = ["docs/commands.md: file not found"]

    errors = check_telegram_commands(tmp_path)

    assert errors == expected, "a missing guide must be reported"
