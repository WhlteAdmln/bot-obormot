# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the installable Python package."""

from pathlib import Path
from zipfile import ZipFile

from build import ProjectBuilder


def test_wheel_contains_prompt_and_excludes_development_files(
    tmp_path: Path,
) -> None:
    project_root = Path(__file__).resolve().parents[3]
    wheel_directory = tmp_path / "wheel"
    wheel_directory.mkdir()

    wheel_name = ProjectBuilder(str(project_root)).build(
        "wheel",
        str(wheel_directory),
    )

    with ZipFile(wheel_directory / wheel_name) as wheel:
        members = wheel.namelist()

        prompt_file = "bot_obormot/prompts/systemPrompt.md"
        assert prompt_file in members
        template_file = "bot_obormot/templates/env.example"
        assert template_file in members
        main_file = "bot_obormot/__main__.py"
        assert main_file in members
        assert not any(path.startswith(("tests/", "scripts/")) for path in members)

        entry_points = [
            path for path in members if path.endswith(".dist-info/entry_points.txt")
        ]
        assert len(entry_points) == 1
        entry_point = "bot-obormot = bot_obormot.cli:main"
        assert entry_point in wheel.read(
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
