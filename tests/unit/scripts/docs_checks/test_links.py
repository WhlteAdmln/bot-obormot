# Copyright (c) 2026 Nikolai Zelensky
"""Tests for Markdown link checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.docs_checks.links import check_markdown_links

if TYPE_CHECKING:
    from pathlib import Path


def test_accepts_links_to_existing_files_and_anchors(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        '[Guide](guide.md#intro-déjà-vu)\n<a href="#top">up</a>\n<a id="top"></a>\n',
        encoding="utf-8",
    )
    (tmp_path / "guide.md").write_text("## Intro: déjà vu\n", encoding="utf-8")
    expected_empty: list[str] = []

    errors = check_markdown_links(tmp_path)

    assert errors == expected_empty, "valid links and anchors must pass"


def test_reports_a_link_to_a_missing_file(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Text\n\n[Lost](docs/missing%20page.md)\n", encoding="utf-8"
    )
    expected = ["README.md:3: broken link 'docs/missing%20page.md'"]

    errors = check_markdown_links(tmp_path)

    assert errors == expected, "a link to a missing file must be reported"


def test_reports_a_link_to_a_missing_anchor(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "[Wrong](guide.md#nowhere-9)\n", encoding="utf-8"
    )
    (tmp_path / "guide.md").write_text("## Somewhere\n", encoding="utf-8")
    expected = ["README.md:1: missing anchor '#nowhere-9' in 'guide.md'"]

    errors = check_markdown_links(tmp_path)

    assert errors == expected, "a link to a missing anchor must be reported"


def test_ignores_links_inside_code(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "`[ghost](ghost.md)`\n```\n[spook](spook.md)\n```\n", encoding="utf-8"
    )
    expected_empty: list[str] = []

    errors = check_markdown_links(tmp_path)

    assert errors == expected_empty, "links inside code must not be checked"
