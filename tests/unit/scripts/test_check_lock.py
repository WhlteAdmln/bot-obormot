# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for check lock."""

from pathlib import Path

from scripts.check_lock import check_lock


def test_check_lock_accepts_satisfied_constraints(tmp_path: Path) -> None:
    """Check lock accepts satisfied constraints."""
    project = tmp_path / "pyproject.toml"
    lock = tmp_path / "requirements-lock.txt"
    project.write_text(
        "[project]\n"
        'dependencies = ["Example_Package[extra]>=1.2,<2.0", "other~=3.1"]\n',
        encoding="utf-8",
    )
    lock.write_text(
        "example-package==1.5.0\nother==3.1.4\n",
        encoding="utf-8",
    )

    assert not check_lock(project, lock)


def test_check_lock_reports_missing_direct_dependency(tmp_path: Path) -> None:
    """Check lock reports missing direct dependency."""
    project = tmp_path / "pyproject.toml"
    lock = tmp_path / "requirements-lock.txt"
    project.write_text(
        '[project]\ndependencies = ["missing-package>=1"]\n',
        encoding="utf-8",
    )
    lock.write_text("present-package==1.0\n", encoding="utf-8")

    assert check_lock(project, lock) == ["Missing from lock file: missing-package"]


def test_check_lock_reports_out_of_range_version(tmp_path: Path) -> None:
    """Check lock reports out of range version."""
    project = tmp_path / "pyproject.toml"
    lock = tmp_path / "requirements-lock.txt"
    project.write_text(
        '[project]\ndependencies = ["example-package>=2,<3"]\n',
        encoding="utf-8",
    )
    lock.write_text("example-package==1.9\n", encoding="utf-8")

    assert check_lock(project, lock) == [
        "Locked example-package==1.9 does not satisfy <3,>=2"
    ]


def test_check_lock_ignores_optional_dependencies(tmp_path: Path) -> None:
    """Check lock ignores optional dependencies."""
    project = tmp_path / "pyproject.toml"
    lock = tmp_path / "requirements-lock.txt"
    project.write_text(
        "[project]\n"
        'dependencies = ["base-package>=1"]\n'
        "[project.optional-dependencies]\n"
        'tgs = ["optional-package>=1"]\n',
        encoding="utf-8",
    )
    lock.write_text("base-package==1.1\n", encoding="utf-8")

    assert not check_lock(project, lock)
