# Copyright (c) 2026 Nikolai Zelensky
"""Tests for the documentation check runner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.check_docs import check_docs

if TYPE_CHECKING:
    from pathlib import Path


def test_runs_the_changelog_check_with_the_documentation_checks(
    tmp_path: Path,
) -> None:
    expected = "CHANGELOG.md: file not found"

    errors = check_docs(tmp_path)

    assert expected in errors, "check_docs must include the changelog order check"


def test_runs_the_code_path_check_with_the_documentation_checks(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("Read `scripts/missing_Ψ.py`.\n", "utf-8")
    expected = "README.md:1: path not found: scripts/missing_Ψ.py"

    errors = check_docs(tmp_path)

    assert expected in errors, "check_docs must include the code path check"
