# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for check lock."""

from pathlib import Path

from scripts.check_lock import check_lock


def test_check_lock_accepts_satisfied_constraints(tmp_path: Path) -> None:
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

    expected_empty: list[str] = []
    assert check_lock(project, lock) == expected_empty, "expected an empty list"


def test_check_lock_reports_missing_direct_dependency(tmp_path: Path) -> None:
    project = tmp_path / "pyproject.toml"
    lock = tmp_path / "requirements-lock.txt"
    project.write_text(
        '[project]\ndependencies = ["missing-package>=1"]\n',
        encoding="utf-8",
    )
    lock.write_text("present-package==1.0\n", encoding="utf-8")

    expected_problems = ["Missing from lock file: missing-package"]
    assert check_lock(project, lock) == expected_problems, (
        "missing package not reported"
    )


def test_check_lock_reports_out_of_range_version(tmp_path: Path) -> None:
    project = tmp_path / "pyproject.toml"
    lock = tmp_path / "requirements-lock.txt"
    project.write_text(
        '[project]\ndependencies = ["example-package>=2,<3"]\n',
        encoding="utf-8",
    )
    lock.write_text("example-package==1.9\n", encoding="utf-8")

    expected_problems = ["Locked example-package==1.9 does not satisfy <3,>=2"]
    assert check_lock(project, lock) == expected_problems, "bad version not reported"


def test_check_lock_ignores_optional_dependencies(tmp_path: Path) -> None:
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

    expected_empty: list[str] = []
    assert check_lock(project, lock) == expected_empty, "expected an empty list"
