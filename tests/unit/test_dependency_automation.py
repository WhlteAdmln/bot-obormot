# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the dependency update automation policy."""

import json
from pathlib import Path
from typing import Any

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(name="renovate_config")
def renovate_config_fixture() -> dict[str, Any]:
    """Load the Renovate configuration without its full-line comments."""
    lines = (ROOT_DIR / ".github" / "renovate.json5").read_text("utf-8").splitlines()
    text = "\n".join(line for line in lines if not line.lstrip().startswith("//"))
    config: dict[str, Any] = json.loads(text)
    return config


def test_renovate_extends_best_practices(renovate_config: dict[str, Any]) -> None:
    """Renovate pins actions and images by digest through the shared preset."""
    assert "config:best-practices" in renovate_config["extends"]


def test_renovate_merges_pull_requests_itself(
    renovate_config: dict[str, Any],
) -> None:
    """Renovate performs the automerge itself."""
    assert renovate_config["automerge"] is True


def test_renovate_does_not_use_platform_automerge(
    renovate_config: dict[str, Any],
) -> None:
    """GitHub platform automerge stays disabled."""
    assert renovate_config["platformAutomerge"] is False


def test_renovate_waits_for_status_checks(renovate_config: dict[str, Any]) -> None:
    """Automerge never skips the required checks."""
    assert renovate_config["ignoreTests"] is False


def test_renovate_requires_fourteen_day_old_releases(
    renovate_config: dict[str, Any],
) -> None:
    """New releases wait 14 days before a pull request is opened."""
    assert renovate_config["minimumReleaseAge"] == "14 days"


def test_renovate_security_fixes_skip_the_release_age(
    renovate_config: dict[str, Any],
) -> None:
    """Vulnerability fixes are proposed without the release age delay."""
    assert renovate_config["vulnerabilityAlerts"]["minimumReleaseAge"] is None


def test_renovate_never_automerges_major_updates(
    renovate_config: dict[str, Any],
) -> None:
    """A major update always needs a human."""
    major_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if rule.get("matchUpdateTypes") == ["major"]
    ]

    assert [rule["automerge"] for rule in major_rules] == [False]


def test_dependabot_version_updates_are_removed() -> None:
    """Dependabot only reports alerts; Renovate opens the update pull requests."""
    assert not (ROOT_DIR / ".github" / "dependabot.yml").exists()
