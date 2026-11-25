# Copyright (c) 2026 Nikolai Zelensky
"""Tests for the pull request size report."""

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.report_pr_size import count_changed_lines, main


def _git(repo: Path, *args: str) -> None:
    git = shutil.which("git") or "git"
    subprocess.run(  # noqa: S603  # fixed git argv, shell=False
        [git, "-c", "user.name=Tester", "-c", "user.email=t@example.org", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _commit(repo: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(repo, "add", "--all")
    _git(repo, "commit", "--quiet", "--no-verify", "--message", "change")


@pytest.fixture(name="repo")
def fixture_repo(tmp_path: Path) -> Path:
    """Create a repository on the branch trunk with one committed file."""
    _git(tmp_path, "init", "--quiet", "--initial-branch=trunk")
    _commit(tmp_path, {"notes/plan.txt": "alpha\nbeta\ngamma\n"})
    return tmp_path


def test_counts_insertions_and_deletions(repo: Path) -> None:
    _commit(repo, {"notes/plan.txt": "alpha\nBETA\ngamma\ndelta\nepsilon\n"})

    expected_lines = 4

    lines = count_changed_lines(repo, "trunk~1")

    assert lines == expected_lines, (
        "three insertions and one deletion make four changed lines"
    )


def test_skips_the_lock_file(repo: Path) -> None:
    _commit(repo, {"requirements-lock.txt": "idna==3.7\nsix==1.16.0\n", "x.py": "1\n"})

    lines = count_changed_lines(repo, "trunk~1")

    assert lines == 1, "requirements-lock.txt must not count"


def test_skips_russian_translations(repo: Path) -> None:
    _commit(repo, {"docs/guide.ru.md": "Привет\nмир\n", "docs/guide.md": "Hi\n"})

    lines = count_changed_lines(repo, "trunk~1")

    assert lines == 1, "a .ru.md translation in a subdirectory must not count"


def test_skips_files_marked_as_generated(repo: Path) -> None:
    _commit(repo, {".gitattributes": "api/*.json linguist-generated=true\n"})
    _commit(repo, {"api/schema.json": '{\n  "openapi": "3.1.0"\n}\n'})

    lines = count_changed_lines(repo, "trunk~1")

    assert lines == 0, "a linguist-generated file must not count"


def test_counts_a_pure_rename_as_no_change(repo: Path) -> None:
    _git(repo, "mv", "notes/plan.txt", "notes/roadmap.txt")
    _git(repo, "commit", "--quiet", "--no-verify", "--message", "rename")

    lines = count_changed_lines(repo, "trunk~1")

    assert lines == 0, "a rename without edits changes no lines"


def test_prints_the_count_and_the_limit(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _commit(repo, {"notes/extra.txt": "one\ntwo\n"})
    monkeypatch.chdir(repo)

    main(["--base", "trunk~1"])

    assert capsys.readouterr().out.startswith("Changed lines: 2 (limit 256;"), (
        "the report must show the count and the limit"
    )


def test_reports_an_unknown_base_instead_of_a_count(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(repo)
    missing_base = "no-such-revision-7f3"

    main(["--base", missing_base])

    assert capsys.readouterr().out.startswith("Cannot measure"), (
        "an unknown base must be reported, not counted"
    )
