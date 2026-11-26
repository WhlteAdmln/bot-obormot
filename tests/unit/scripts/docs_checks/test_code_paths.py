# Copyright (c) 2026 Nikolai Zelensky
"""Tests for the documentation code path check."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.docs_checks.code_paths import check_code_paths

if TYPE_CHECKING:
    from pathlib import Path


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_accepts_paths_that_exist(tmp_path: Path) -> None:
    _write(tmp_path, "bot_obormot/services/väter.py", "")
    readme = "Модуль `bot_obormot/services/väter.py` и `bot_obormot/services/`.\n"
    _write(tmp_path, "README.md", readme)
    expected_empty: list[str] = []

    errors = check_code_paths(tmp_path)

    assert errors == expected_empty, "existing files and directories must pass"


def test_reports_a_missing_path_with_file_and_line(tmp_path: Path) -> None:
    guide = "# Архитектура\n\nSee `bot_obormot/gone/Qx7.py` here.\n"
    _write(tmp_path, "docs/architecture.ru.md", guide)
    expected = ["docs/architecture.ru.md:3: path not found: bot_obormot/gone/Qx7.py"]

    errors = check_code_paths(tmp_path)

    assert errors == expected, "a missing path must be reported with its line"


def test_checks_each_segment_of_a_command(tmp_path: Path) -> None:
    contributing = "Run `python scripts/äbsent_9.py --other ../elsewhere`.\n"
    _write(tmp_path, "CONTRIBUTING.md", contributing)
    expected = ["CONTRIBUTING.md:1: path not found: scripts/äbsent_9.py"]

    errors = check_code_paths(tmp_path)

    assert errors == expected, "a path inside a command must be checked"


def test_drops_a_function_name_suffix(tmp_path: Path) -> None:
    _write(tmp_path, "bot_obormot/common/text_z.py", "")
    readme = "Use `bot_obormot/common/text_z.py::log_safe()`.\n"
    _write(tmp_path, "README.ru.md", readme)
    expected_empty: list[str] = []

    errors = check_code_paths(tmp_path)

    assert errors == expected_empty, "a ::name() suffix must not be part of the path"


def test_skips_a_segment_with_a_placeholder(tmp_path: Path) -> None:
    readme = "Tests live in `tests/unit/<package>/test_<module>.py`.\n"
    _write(tmp_path, "docs/testing/Layout.md", readme)
    expected_empty: list[str] = []

    errors = check_code_paths(tmp_path)

    assert errors == expected_empty, "a placeholder path must be skipped"


def test_ignores_fenced_code_blocks(tmp_path: Path) -> None:
    readme = "Intro\n\n```text\nline with `scripts/nowhere_31.sh`\n```\n"
    _write(tmp_path, "README.md", readme)
    expected_empty: list[str] = []

    errors = check_code_paths(tmp_path)

    assert errors == expected_empty, "fenced code must not be checked"


def test_ignores_documents_outside_the_checked_set(tmp_path: Path) -> None:
    _write(tmp_path, "CHANGELOG.md", "- Removed `tests/unit/old_Ω.py`.\n")
    _write(tmp_path, "AGENTS.md", "Example `bot_obormot/a/b.py`.\n")
    expected_empty: list[str] = []

    errors = check_code_paths(tmp_path)

    assert errors == expected_empty, "the changelog and agent files must be skipped"
