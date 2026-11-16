# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the installable Python package."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from bot import cli
from build import ProjectBuilder


def test_cli_main_runs_application(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runs the application through the console entry point."""
    calls = 0

    async def fake_run_bot() -> None:
        """Record that the application coroutine was executed."""
        nonlocal calls
        calls += 1

    monkeypatch.setattr(cli, "run_bot", fake_run_bot)
    cli.main()

    assert calls == 1


def test_wheel_contains_prompt_and_excludes_development_files(
    tmp_path: Path,
) -> None:
    """Builds a wheel with package data and without repository-only paths."""
    project_root = Path(__file__).resolve().parents[2]
    wheel_directory = tmp_path / "wheel"
    wheel_directory.mkdir()

    wheel_name = ProjectBuilder(str(project_root)).build(
        "wheel",
        str(wheel_directory),
    )

    with ZipFile(wheel_directory / wheel_name) as wheel:
        members = wheel.namelist()

        assert "bot/prompts/systemPrompt.md" in members
        assert not any(path.startswith(("tests/", "scripts/")) for path in members)

        entry_points = [
            path for path in members if path.endswith(".dist-info/entry_points.txt")
        ]
        assert len(entry_points) == 1
        assert "bot-obormot = bot.cli:main" in wheel.read(
            entry_points[0],
        ).decode("utf-8")

        metadata_path = next(
            path for path in members if path.endswith(".dist-info/METADATA")
        )
        metadata = wheel.read(metadata_path).decode("utf-8").lower()
        runtime_dependencies = (
            "aiogram",
            "aiohttp",
            "aiosqlite",
            "python-dotenv",
            "pillow",
        )
        for dependency in runtime_dependencies:
            assert f"requires-dist: {dependency}" in metadata
