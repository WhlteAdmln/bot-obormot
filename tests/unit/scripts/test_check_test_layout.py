# Copyright (c) 2026 Nikolai Zelensky
"""Tests for the test layout check."""

from pathlib import Path

import pytest

from scripts import check_test_layout


@pytest.fixture(name="project")
def project_fixture(tmp_path: Path) -> Path:
    """Build a minimal repository with one package and an empty unit test tree."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo-app"\n')
    (tmp_path / "demo_app" / "api").mkdir(parents=True)
    (tmp_path / "demo_app" / "api" / "auth.py").write_text("class TokenChecker: ...\n")
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    return tmp_path


def _add_test(project: Path, relative: str) -> None:
    """Create an empty unit test file below tests/unit."""
    path = project / "tests" / "unit" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")


def test_accepts_test_file_at_the_path_of_its_module(project: Path) -> None:
    _add_test(project, "api/test_auth.py")
    problems = check_test_layout.find_problems(project)
    assert not problems, "a test next to its module path must pass"


def test_accepts_test_file_named_after_a_class(project: Path) -> None:
    _add_test(project, "api/test_token_checker.py")
    problems = check_test_layout.find_problems(project)
    assert not problems, "a snake_case class name must identify the unit"


def test_accepts_test_file_in_project_directory(project: Path) -> None:
    _add_test(project, "project/test_release_notes.py")
    problems = check_test_layout.find_problems(project)
    assert not problems, "tests of the project itself need no production unit"


def test_reports_test_file_without_production_unit(project: Path) -> None:
    _add_test(project, "test_everything.py")
    problems = check_test_layout.find_problems(project)
    assert problems == [
        "tests/unit/test_everything.py: no production unit at the mirrored path"
    ], "a test without a unit must be reported once"


def test_tolerates_pending_file_that_breaks_the_layout(project: Path) -> None:
    _add_test(project, "test_everything.py")
    (project / "tests" / "layout_pending.txt").write_text(
        "tests/unit/test_everything.py\n"
    )
    problems = check_test_layout.find_problems(project)
    assert not problems, "a listed file is allowed to break the layout"


def test_reports_pending_file_that_already_mirrors_a_unit(project: Path) -> None:
    _add_test(project, "api/test_auth.py")
    (project / "tests" / "layout_pending.txt").write_text(
        "tests/unit/api/test_auth.py\n"
    )
    problems = check_test_layout.find_problems(project)
    assert problems == [
        "tests/unit/api/test_auth.py: already mirrors a unit; remove it from the list"
    ], "a fixed file must leave the list"


def test_reports_pending_file_that_does_not_exist(project: Path) -> None:
    (project / "tests" / "layout_pending.txt").write_text("tests/unit/test_gone.py\n")
    problems = check_test_layout.find_problems(project)
    assert problems == [
        (
            "tests/unit/test_gone.py: listed in tests/layout_pending.txt but the "
            "file does not exist"
        )
    ], "a removed file must leave the list"


@pytest.mark.parametrize(
    ("class_name", "expected"),
    [("LLMClient", "llm_client"), ("StreamingResponder", "streaming_responder")],
)
def test_converts_class_names_to_snake_case(class_name: str, expected: str) -> None:
    assert check_test_layout.snake_case(class_name) == expected, "unexpected name"
