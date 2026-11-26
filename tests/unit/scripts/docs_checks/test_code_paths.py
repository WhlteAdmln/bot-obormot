# Copyright (c) 2026 Nikolai Zelensky
"""Tests for the documentation code path check."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scripts.docs_checks.code_paths import check_code_paths

if TYPE_CHECKING:
    from pathlib import Path


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_project(root: Path, project_name: str) -> None:
    _write(root, "pyproject.toml", f'[project]\nname = "{project_name}"\n')


@pytest.mark.parametrize(
    ("document", "text"),
    [
        ("README.md", "Run `scripts/tidy_up.py` first."),
        ("docs/guide.md", "See `marsh_wren/engine/` for the engine."),
        ("CONTRIBUTING.ru.md", "Вызовите `scripts/tidy_up.py::sweep_dust()`."),
        ("docs/deep/notes.md", "Use `scripts/tidy_up.py --base HEAD^1` here."),
        ("docs/plugins.md", "Add `marsh_wren/engine/<name>.py` for a format."),
        ("docs/setup.md", "Copy `deploy/unit.example` and `tests` aside."),
        ("docs/runner.md", "Call `make check tests/unit/gone_by.py` again."),
        ("docs/other.md", "Unlike `other_pkg/lost_Ω.py` in a fork."),
        ("docs/fenced.md", "```text\n`tests/gone_away.py`\n```\n"),
        ("CHANGELOG.md", "- Removed `scripts/retired_tool.py`."),
        ("AGENTS.md", "Mirror `marsh_wren/a/b.py` in tests."),
    ],
)
def test_accepts_documents_without_missing_paths(
    tmp_path: Path, document: str, text: str
) -> None:
    _write_project(tmp_path, "marsh-wren")
    _write(tmp_path, "scripts/tidy_up.py", "")
    _write(tmp_path, "marsh_wren/engine/core.py", "")
    _write(tmp_path, document, text)
    expected_empty: list[str] = []

    errors = check_code_paths(tmp_path)

    assert errors == expected_empty, f"{document} must not report a path"


def test_reports_a_missing_path_with_its_line(tmp_path: Path) -> None:
    text = "# Matrix\n\nRows: `tests/unit/old_matrix.py`.\n"
    _write_project(tmp_path, "quill")
    _write(tmp_path, "docs/matrix.md", text)
    expected = ["docs/matrix.md:3: missing path 'tests/unit/old_matrix.py'"]

    errors = check_code_paths(tmp_path)

    assert errors == expected, "a stale path must be reported with file and line"


def test_reports_a_missing_path_after_a_fenced_block(tmp_path: Path) -> None:
    text = "```sh\nmake check\n```\n\nSee `scripts/vanished.py::run()`.\n"
    _write_project(tmp_path, "fern-gate")
    _write(tmp_path, "README.ru.md", text)
    expected = ["README.ru.md:5: missing path 'scripts/vanished.py'"]

    errors = check_code_paths(tmp_path)

    assert errors == expected, "line numbers must count the lines of fenced blocks"


def test_reports_a_missing_path_of_the_project_package(tmp_path: Path) -> None:
    text = "Модуль `slate_otter_kit/gone/Qx7.py` удалён.\n"
    _write_project(tmp_path, "slate-otter-kit")
    _write(tmp_path, "docs/architecture.ru.md", text)
    expected = ["docs/architecture.ru.md:1: missing path 'slate_otter_kit/gone/Qx7.py'"]

    errors = check_code_paths(tmp_path)

    assert errors == expected, "the package prefix must follow the project name"
