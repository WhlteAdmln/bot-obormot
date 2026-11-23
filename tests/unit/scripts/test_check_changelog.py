# Copyright (c) 2026 Nikolai Zelensky
"""Tests for the changelog section order check."""

from pathlib import Path

from scripts.check_changelog import check_changelog


def test_accepts_sections_in_the_project_order(tmp_path: Path) -> None:
    text = (
        "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- a\n\n### Changed\n\n- c\n\n"
        "### Deprecated\n\n- d\n\n### Fixed\n\n- f\n\n### Removed\n\n- r\n\n"
        "### Security\n\n- s\n"
    )
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")

    errors = check_changelog(tmp_path)

    assert not errors, "sections in the project order must be accepted"


def test_accepts_versions_with_omitted_sections(tmp_path: Path) -> None:
    text = "## [1.2.0] - 2026-01-02\n\n### Fixed\n\n- f\n\n### Security\n\n- s\n"
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")

    errors = check_changelog(tmp_path)

    assert not errors, "a version may leave out any section"


def test_reports_section_that_comes_after_a_later_one(tmp_path: Path) -> None:
    text = "## [3.1.4] - 2026-03-14\n\n### Removed\n\n- r\n\n### Changed\n\n- c\n"
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    expected = "CHANGELOG.md: [3.1.4]: section 'Changed' must come before 'Removed'"

    errors = check_changelog(tmp_path)

    assert errors == [expected], "the error must name version, section and place"


def test_reports_section_repeated_in_one_version(tmp_path: Path) -> None:
    text = "## [0.7.0] - 2026-07-07\n\n### Added\n\n- a\n\n### Added\n\n- b\n"
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    expected = "CHANGELOG.md: [0.7.0]: duplicate section 'Added'"

    errors = check_changelog(tmp_path)

    assert errors == [expected], "a repeated section must be reported once"


def test_reports_section_with_an_unknown_name(tmp_path: Path) -> None:
    text = "## [Unreleased]\n\n### Improved\n\n- i\n"
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    expected = (
        "CHANGELOG.md: [Unreleased]: unknown section 'Improved'; expected one of "
        "Added, Changed, Deprecated, Fixed, Removed, Security"
    )

    errors = check_changelog(tmp_path)

    assert errors == [expected], "an unknown section must list the valid names"


def test_ignores_a_parenthesized_suffix_in_a_section_name(tmp_path: Path) -> None:
    text = "## [0.4.2] - 2026-04-02\n\n### Added (0.4.2)\n\n- a\n\n### Fixed (CLI)\n"
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")

    errors = check_changelog(tmp_path)

    assert not errors, "a suffix in parentheses must not change the section name"


def test_checks_every_version_on_its_own(tmp_path: Path) -> None:
    text = (
        "## [2.0.0] - 2026-02-01\n\n### Security\n\n- s\n\n"
        "## [1.0.0] - 2026-01-01\n\n### Security\n\n- s\n"
    )
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")

    errors = check_changelog(tmp_path)

    assert not errors, "the same section in two versions is not a duplicate"


def test_ignores_headings_inside_code_blocks(tmp_path: Path) -> None:
    text = "## [5.0.0] - 2026-05-05\n\n```markdown\n### Nonsense\n```\n\n### Added\n"
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")

    errors = check_changelog(tmp_path)

    assert not errors, "a heading inside a fenced block is not a section"


def test_reports_section_that_is_outside_any_version(tmp_path: Path) -> None:
    text = "# Changelog\n\n### Added\n\n- a\n"
    (tmp_path / "CHANGELOG.md").write_text(text, encoding="utf-8")
    expected = "CHANGELOG.md: section 'Added' is outside a version"

    errors = check_changelog(tmp_path)

    assert errors == [expected], "a section needs a version heading above it"


def test_reports_a_missing_changelog_file(tmp_path: Path) -> None:
    expected = "CHANGELOG.md: file not found"

    errors = check_changelog(tmp_path)

    assert errors == [expected], "a missing file must be reported"
