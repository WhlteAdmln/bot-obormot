# Copyright (c) 2026 Nikolai Zelensky
"""Tests for finding Markdown documents and their code."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.docs_checks.markdown import (
    code_segments,
    display_path,
    markdown_files,
    without_code,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_lists_markdown_files_outside_ignored_directories(tmp_path: Path) -> None:
    kept = tmp_path / "docs" / "Notes-7.md"
    skipped = tmp_path / ".venv" / "lib" / "Vendored README.md"
    kept.parent.mkdir()
    skipped.parent.mkdir(parents=True)
    kept.write_text("# Заметки\n", encoding="utf-8")
    skipped.write_text("# Vendored\n", encoding="utf-8")
    expected = [kept]

    found = markdown_files(tmp_path)

    assert found == expected, "only files outside ignored directories are listed"


def test_removes_code_and_keeps_the_line_count() -> None:
    text = "Intro ½\n```sh\nrm -rf /tmp/x\n```\nend `[a](b.md)` tail"
    expected = "Intro ½\n\n\n\nend  tail"

    cleaned = without_code(text)

    assert cleaned == expected, "code is removed and line breaks are kept"


def test_extracts_fenced_and_inline_code_segments() -> None:
    text = "Run:\n~~~~\nmake  check\n~~~~\nthen `git status -s` or `ls`.\n"
    expected = ["make  check\n", "git status -s", "ls"]

    segments = code_segments(text)

    assert segments == expected, "fenced blocks come first, then inline code"


def test_shows_a_path_outside_the_root_as_it_is(tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere" / "Ü.md"
    expected = outside.as_posix()

    shown = display_path(outside, tmp_path)

    assert shown == expected, "a path outside the root is not made relative"
