# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the installable Python package."""

import shutil
from pathlib import Path
from zipfile import ZipFile

import pytest
from build import ProjectBuilder


@pytest.fixture(name="wheel_path")
def fixture_wheel_path(tmp_path: Path) -> Path:
    """Build the project wheel from a copy of the project in a temporary directory."""
    project_root = Path(__file__).resolve().parents[3]
    project_copy = tmp_path / "project"
    shutil.copytree(
        project_root,
        project_copy,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".*cache*",
            ".hypothesis",
            "__pycache__",
            "*.egg-info",
            "build",
            "dist",
        ),
    )
    wheel_directory = tmp_path / "wheel"
    wheel_directory.mkdir()
    wheel_name = ProjectBuilder(str(project_copy)).build(
        "wheel",
        str(wheel_directory),
    )
    return wheel_directory / wheel_name


def _members(wheel_path: Path) -> list[str]:
    with ZipFile(wheel_path) as wheel:
        return wheel.namelist()


def _dist_info_text(wheel_path: Path, suffix: str) -> str:
    with ZipFile(wheel_path) as wheel:
        member = next(path for path in wheel.namelist() if path.endswith(suffix))
        return wheel.read(member).decode("utf-8")


@pytest.mark.parametrize(
    "packaged_file",
    [
        "bot_obormot/prompts/systemPrompt.md",
        "bot_obormot/templates/env.example",
        "bot_obormot/__main__.py",
    ],
)
def test_wheel_contains_runtime_file(wheel_path: Path, packaged_file: str) -> None:
    assert packaged_file in _members(wheel_path), f"{packaged_file} is not packaged"


def test_wheel_excludes_development_files(wheel_path: Path) -> None:
    development_prefixes = ("tests/", "scripts/")
    assert not any(
        path.startswith(development_prefixes) for path in _members(wheel_path)
    ), "wheel contains tests or scripts"


def test_wheel_has_one_entry_points_file(wheel_path: Path) -> None:
    entry_points_suffix = ".dist-info/entry_points.txt"
    entry_points = [
        path for path in _members(wheel_path) if path.endswith(entry_points_suffix)
    ]
    expected_count = 1
    assert len(entry_points) == expected_count, "wrong number of entry point files"


def test_wheel_declares_the_console_script(wheel_path: Path) -> None:
    entry_points_suffix = ".dist-info/entry_points.txt"
    entry_point = "bot-obormot = bot_obormot.cli:main"
    assert entry_point in _dist_info_text(wheel_path, entry_points_suffix), (
        "console script is not declared"
    )


@pytest.mark.parametrize(
    "dependency",
    ["aiogram", "aiohttp", "aiosqlite", "python-dotenv", "pillow"],
)
def test_wheel_requires_runtime_dependency(wheel_path: Path, dependency: str) -> None:
    metadata_suffix = ".dist-info/METADATA"
    metadata = _dist_info_text(wheel_path, metadata_suffix).lower()
    assert f"requires-dist: {dependency}" in metadata, (
        f"{dependency} is not a declared dependency"
    )
