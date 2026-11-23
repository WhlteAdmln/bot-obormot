# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for documentation consistency checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from scripts.check_docs import (
    DOCUMENTATION_ONLY_ENV_NAMES,
    _settings_environment_names,
    check_documented_commands,
    check_markdown_links,
    check_russian_documents,
    check_section_parity,
    check_settings,
    check_telegram_commands,
)


def test_markdown_links_check_local_files_and_anchors(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    guide = tmp_path / "guide.md"
    readme.write_text("[Guide](guide.md#intro)\n", encoding="utf-8")
    guide.write_text("## Intro\n", encoding="utf-8")

    assert check_markdown_links(tmp_path) == []

    readme.write_text(
        "[Missing](missing.md)\n[Wrong anchor](guide.md#missing)\n",
        encoding="utf-8",
    )
    errors = check_markdown_links(tmp_path)

    assert len(errors) == 2
    assert any("missing.md" in error for error in errors)
    assert any("#missing" in error for error in errors)


def test_russian_sections_keep_the_same_order(tmp_path: Path) -> None:
    english = tmp_path / "guide.md"
    russian = tmp_path / "guide.ru.md"
    english.write_text("## 1. First\n## 2. Second\n", encoding="utf-8")
    russian.write_text("## 1. Первый\n## 2. Второй\n", encoding="utf-8")

    assert check_section_parity(tmp_path) == []

    russian.write_text("## 2. Второй\n## 1. Первый\n", encoding="utf-8")
    assert check_section_parity(tmp_path)


def test_russian_documents_must_contain_cyrillic(tmp_path: Path) -> None:
    russian = tmp_path / "guide.ru.md"
    russian.write_text("# Руководство\n", encoding="utf-8")

    assert check_russian_documents(tmp_path) == []

    russian.write_text("# Guide\n", encoding="utf-8")
    assert check_russian_documents(tmp_path)


def test_settings_match_env_example_and_configuration_reference(
    tmp_path: Path,
) -> None:
    names = _settings_environment_names()
    env_path = tmp_path / ".env.example"
    env_path.write_text(
        "\n".join(f"{name}=" for name in sorted(names)) + "\n",
        encoding="utf-8",
    )

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    docs_path = docs_dir / "configuration.md"
    documented_names = names | DOCUMENTATION_ONLY_ENV_NAMES
    rows = "\n".join(f"| `{name}` | value |" for name in sorted(documented_names))
    docs_path.write_text(
        "## Environment settings\n"
        "| Variable | Default |\n"
        "| --- | --- |\n" + rows + "\n",
        encoding="utf-8",
    )

    assert check_settings(tmp_path) == []

    env_path.write_text("LOG_LEVEL=INFO\n", encoding="utf-8")
    assert check_settings(tmp_path)


def test_documented_commands_must_exist_in_cli_help(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "Use `bot-obormot init --supervisor 42`.\n",
        encoding="utf-8",
    )

    assert check_documented_commands(tmp_path) == []

    readme.write_text("Use `bot-obormot unknown-command`.\n", encoding="utf-8")
    assert check_documented_commands(tmp_path)


def test_documented_commands_ignore_environment_paths_ending_in_bot_obormot(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "BOT_OBORMOT_HOME=/opt/bot-obormot "
        "/opt/bot-obormot/.venv/bin/bot-obormot service install --system --print\n"
        "sudo env BOT_OBORMOT_HOME=/opt/bot-obormot "
        "/opt/bot-obormot/.venv/bin/bot-obormot service install --system\n",
        encoding="utf-8",
    )

    assert check_documented_commands(tmp_path) == []


def test_telegram_commands_must_appear_in_the_commands_guide(tmp_path: Path) -> None:
    package_dir = tmp_path / "bot_obormot"
    docs_dir = tmp_path / "docs"
    package_dir.mkdir()
    docs_dir.mkdir()
    (package_dir / "handler.py").write_text(
        'router.message(Command("start"))\nrouter.message(Command("history_limit"))\n',
        encoding="utf-8",
    )
    guide = docs_dir / "commands.md"
    guide.write_text("`/start`\n`/history_limit N`\n", encoding="utf-8")

    assert check_telegram_commands(tmp_path) == []

    guide.write_text("`/start`\n", encoding="utf-8")
    errors = check_telegram_commands(tmp_path)

    assert errors == ["docs/commands.md: missing commands: /history_limit"]
