# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the installable Python package."""

from pathlib import Path
from zipfile import ZipFile

from build import ProjectBuilder


def test_wheel_contains_prompt_and_excludes_development_files(
    tmp_path: Path,
) -> None:
    """Builds a wheel with package data and without repository-only paths."""
    project_root = Path(__file__).resolve().parents[3]
    wheel_directory = tmp_path / "wheel"
    wheel_directory.mkdir()

    wheel_name = ProjectBuilder(str(project_root)).build(
        "wheel",
        str(wheel_directory),
    )

    with ZipFile(wheel_directory / wheel_name) as wheel:
        members = wheel.namelist()

        expected_fragment = "bot_obormot/prompts/systemPrompt.md"
        assert expected_fragment in members
        expected_fragment = "bot_obormot/templates/env.example"
        assert expected_fragment in members
        expected_fragment = "bot_obormot/__main__.py"
        assert expected_fragment in members
        assert not any(path.startswith(("tests/", "scripts/")) for path in members)

        entry_points = [
            path for path in members if path.endswith(".dist-info/entry_points.txt")
        ]
        assert len(entry_points) == 1
        expected_fragment = "bot-obormot = bot_obormot.cli:main"
        assert expected_fragment in wheel.read(
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
