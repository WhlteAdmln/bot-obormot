# Copyright (c) 2026 Nikolai Zelensky
"""Tests for the vendored-file consistency check."""

import json
from pathlib import Path

import pytest

from scripts.check_vendored import (
    HEADERLESS_VENDORED_FILES,
    PACKAGE_VENDORED_FILES,
    PYPROJECT_FILE,
    VENDORED_FILES,
    VENDORED_HEADER,
    check_vendored,
    main,
)


def _pyproject(package_name: str, line_length: int, addopts: str) -> str:
    return (
        f"{VENDORED_HEADER}\n\n"
        "[tool.ruff]\n"
        f"line-length = {line_length}\n\n"
        "[tool.ruff.lint.isort]\n"
        f"known-first-party = [{json.dumps(package_name)}]\n\n"
        "[tool.mypy]\n"
        f"packages = [{json.dumps(package_name + '.core')}]\n\n"
        "[tool.deptry]\n"
        f"known_first_party = [{json.dumps(package_name)}]\n\n"
        "[tool.pytest.ini_options]\n"
        f"addopts = {json.dumps(addopts)}\n"
    )


def _write_repository(
    root: Path,
    package_name: str,
    *,
    line_length: int = 88,
    addopts: str = "-q",
) -> Path:
    for relative_path in VENDORED_FILES:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            _pyproject(package_name, line_length, addopts)
            if relative_path == PYPROJECT_FILE
            else f"{VENDORED_HEADER}\nwren lantern {relative_path}\n"
        )
        path.write_text(content, encoding="utf-8")

    for relative_path in HEADERLESS_VENDORED_FILES:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"oxbow quarry {relative_path}\n", encoding="utf-8")

    package_dir = root / package_name
    package_dir.mkdir(parents=True, exist_ok=True)
    for filename in PACKAGE_VENDORED_FILES:
        (package_dir / filename).write_text(
            f"{VENDORED_HEADER}\nheron sluice {filename}\n",
            encoding="utf-8",
        )
    return root.resolve()


@pytest.fixture(name="local")
def fixture_local(tmp_path: Path) -> Path:
    """Create the repository that runs the check."""
    return _write_repository(tmp_path / "kestrel-mill", "kestrel_mill")


@pytest.fixture(name="other")
def fixture_other(tmp_path: Path) -> Path:
    """Create the sibling repository with another package name."""
    return _write_repository(tmp_path / "umber-fjord", "umber_fjord")


def test_accepts_identical_repositories(local: Path, other: Path) -> None:
    expected_empty: list[str] = []

    errors = check_vendored(other, root=local)

    assert errors == expected_empty, "identical shared files must not be reported"


def test_ignores_settings_outside_the_lint_tables(local: Path, tmp_path: Path) -> None:
    other = _write_repository(
        tmp_path / "sorrel-ditch", "sorrel_ditch", addopts="-vv --maxfail=7"
    )
    expected_empty: list[str] = []

    errors = check_vendored(other, root=local)

    assert errors == expected_empty, "pytest options are not part of the lint check"


def test_reports_a_lint_configuration_difference(local: Path, tmp_path: Path) -> None:
    other = _write_repository(tmp_path / "flint-moor", "flint_moor", line_length=97)
    expected = ["pyproject.toml: lint configuration differs from other repository"]

    errors = check_vendored(other, root=local)

    assert errors == expected, "a different ruff line length must be reported"


def test_reports_a_lint_difference_beyond_the_package_name(
    local: Path, other: Path
) -> None:
    pyproject = other / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8").replace(
            '"umber_fjord.core"', '"umber_fjordx.core"'
        ),
        encoding="utf-8",
    )
    expected = ["pyproject.toml: lint configuration differs from other repository"]

    errors = check_vendored(other, root=local)

    assert errors == expected, "only whole package names may be normalized"


def test_reports_a_differing_file_with_header(local: Path, other: Path) -> None:
    (other / "scripts/coverage_gaps.py").write_text(
        f"{VENDORED_HEADER}\nbrackish tide\n", encoding="utf-8"
    )
    expected = ["scripts/coverage_gaps.py: content differs from other repository"]

    errors = check_vendored(other, root=local)

    assert errors == expected, "a changed vendored script must be reported"


def test_reports_a_differing_docs_check_module(local: Path, other: Path) -> None:
    (local / "scripts/docs_checks/russian.py").write_text(
        f"{VENDORED_HEADER}\nbirch gully\n", encoding="utf-8"
    )
    expected = ["scripts/docs_checks/russian.py: content differs from other repository"]

    errors = check_vendored(other, root=local)

    assert errors == expected, "a changed shared docs check must be reported"


def test_reports_a_differing_headerless_file(local: Path, other: Path) -> None:
    (local / "AGENTS.md").write_text("# Gannet rules\n", encoding="utf-8")
    expected = ["AGENTS.md: content differs from other repository"]

    errors = check_vendored(other, root=local)

    assert errors == expected, "a changed headerless file must be reported"


def test_reports_a_differing_package_file(local: Path, other: Path) -> None:
    (other / "umber_fjord" / "env_readers.py").write_text(
        f"{VENDORED_HEADER}\nslate cormorant\n", encoding="utf-8"
    )
    expected = ["<package>/env_readers.py: content differs from other repository"]

    errors = check_vendored(other, root=local)

    assert errors == expected, "a changed package module must be reported"


def test_reports_a_missing_file(local: Path, other: Path) -> None:
    missing = other / ".markdownlint-cli2.yaml"
    missing.unlink()
    expected = [f"{missing}: file not found"]

    errors = check_vendored(other, root=local)

    assert errors == expected, "a missing vendored file must be reported"


def test_reports_a_missing_header(local: Path, other: Path) -> None:
    headless = local / ".editorconfig"
    headless.write_text("root = true\n", encoding="utf-8")

    errors = check_vendored(other, root=local)

    assert f"{headless}: missing VENDORED header" in errors, (
        "a vendored file without the header must be reported"
    )


def test_reports_a_repository_without_a_package(local: Path, other: Path) -> None:
    (other / "umber_fjord" / "log_filters.py").unlink()

    expected_error = (
        "other repository: expected exactly one package containing log_filters.py, "
        "found 0"
    )

    errors = check_vendored(other, root=local)

    assert expected_error in errors, (
        "a repository without the shared package must be reported"
    )


def test_reports_a_missing_other_repository(local: Path, tmp_path: Path) -> None:
    absent = tmp_path / "vanished-cairn"
    expected = [f"Other repository does not exist: {absent.resolve()}"]

    errors = check_vendored(absent, root=local)

    assert errors == expected, "a missing other repository must be reported"


def test_main_fails_for_a_missing_other_repository(tmp_path: Path) -> None:
    absent = tmp_path / "hollow-sedge"
    expected_status = 1

    status = main(["--other", str(absent)])

    assert status == expected_status, "the command must fail when the check fails"
