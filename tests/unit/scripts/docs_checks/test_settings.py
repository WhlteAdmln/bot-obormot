# Copyright (c) 2026 Nikolai Zelensky
"""Tests for settings documentation checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.docs_checks.settings import (
    DOCUMENTATION_ONLY_ENV_NAMES,
    check_settings,
    settings_environment_names,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_settings_files(root: Path, example_names: set[str]) -> None:
    (root / ".env.example").write_text(
        "".join(f"export {name}=\n" for name in sorted(example_names)),
        encoding="utf-8",
    )
    documented = settings_environment_names() | DOCUMENTATION_ONLY_ENV_NAMES
    rows = "".join(f"| `{name}` | n/a |\n" for name in sorted(documented))
    (root / "docs").mkdir()
    (root / "docs" / "configuration.md").write_text(
        "| Variable | Default |\n| --- | --- |\n" + rows, encoding="utf-8"
    )


def test_accepts_settings_listed_in_the_example_and_the_guide(tmp_path: Path) -> None:
    _write_settings_files(tmp_path, settings_environment_names())
    expected_empty: list[str] = []

    errors = check_settings(tmp_path)

    assert errors == expected_empty, "complete settings files must pass"


def test_reports_an_unknown_setting_in_the_example(tmp_path: Path) -> None:
    _write_settings_files(tmp_path, settings_environment_names() | {"ZX_KNOB_42"})
    expected = [".env.example: unknown settings: ZX_KNOB_42"]

    errors = check_settings(tmp_path)

    assert errors == expected, "a name that is not a setting must be reported"


def test_reports_missing_settings_files(tmp_path: Path) -> None:
    expected = [".env.example: file not found", "docs/configuration.md: file not found"]

    errors = check_settings(tmp_path)

    assert errors == expected, "both missing files must be reported"
