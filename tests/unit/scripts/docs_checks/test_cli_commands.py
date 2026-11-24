# Copyright (c) 2026 Nikolai Zelensky
"""Tests for documented CLI command checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.docs_checks.cli_commands import check_documented_commands

if TYPE_CHECKING:
    from pathlib import Path


def test_accepts_a_documented_command_that_the_parser_knows(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Use `bot-obormot init --supervisor 42`.\n", encoding="utf-8"
    )
    expected_empty: list[str] = []

    errors = check_documented_commands(tmp_path)

    assert errors == expected_empty, "a known command must pass"


def test_reports_a_documented_command_that_the_parser_rejects(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "```sh\nbot-obormot frobnicate --now && echo ok\n```\n", encoding="utf-8"
    )
    expected = ["README.md: invalid CLI command 'bot-obormot frobnicate --now'"]

    errors = check_documented_commands(tmp_path)

    assert errors == expected, "an unknown command must be reported"


def test_ignores_environment_paths_ending_in_the_command_name(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "BOT_OBORMOT_HOME=/opt/bot-obormot "
        "/opt/bot-obormot/.venv/bin/bot-obormot service install --system --print\n"
        "sudo env BOT_OBORMOT_HOME=/opt/bot-obormot "
        "/opt/bot-obormot/.venv/bin/bot-obormot service install --system\n",
        encoding="utf-8",
    )
    expected_empty: list[str] = []

    errors = check_documented_commands(tmp_path)

    assert errors == expected_empty, "a path in an environment value is not a call"
