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


def test_renovate_refreshes_the_lock_so_transitive_packages_move(
    renovate_config: dict[str, Any],
) -> None:
    """Only a lock refresh updates transitive packages, such as security fixes."""
    assert renovate_config["lockFileMaintenance"]["enabled"] is True


def test_renovate_lock_refresh_is_not_merged_automatically(
    renovate_config: dict[str, Any],
) -> None:
    """A refresh ignores the release age, so a human reviews and merges it."""
    assert renovate_config["lockFileMaintenance"]["automerge"] is False


def test_renovate_lock_refresh_rule_blocks_automerge(
    renovate_config: dict[str, Any],
) -> None:
    """The package rule keeps the refresh out of automerge whatever the defaults."""
    refresh_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if rule.get("matchUpdateTypes") == ["lockFileMaintenance"]
    ]

    assert [rule["automerge"] for rule in refresh_rules] == [False]


def test_renovate_regenerates_the_lock_with_pip_compile(
    renovate_config: dict[str, Any],
) -> None:
    """requirements-lock.txt carries a uv header, so pip-compile owns the file."""
    assert "pip-compile" in renovate_config["enabledManagers"]


def test_renovate_does_not_edit_the_lock_line_by_line(
    renovate_config: dict[str, Any],
) -> None:
    """Pins without a resolver could break the lock, so pip_requirements is off."""
    assert "pip_requirements" not in renovate_config["enabledManagers"]


def test_renovate_python_version_changes_are_left_to_humans(
    renovate_config: dict[str, Any],
) -> None:
    """Supported Python versions and the image base are never bumped by a bot."""
    python_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if rule.get("matchDepNames") == ["python"]
    ]

    assert [rule["enabled"] for rule in python_rules] == [False]


def test_lock_command_writes_options_with_equal_signs() -> None:
    """Renovate refuses a lock header whose long options lack an equal sign."""
    makefile = (ROOT_DIR / "Makefile").read_text("utf-8")

    assert "--python-version=$(LOCK_PYTHON_VERSION)" in makefile


def test_lock_command_names_the_output_file_with_an_equal_sign() -> None:
    """The header must name the output file in the form Renovate parses."""
    makefile = (ROOT_DIR / "Makefile").read_text("utf-8")

    assert "--output-file=requirements-lock.txt" in makefile


def test_renovate_updates_pydantic_and_its_core_together(
    renovate_config: dict[str, Any],
) -> None:
    """The two packages pin each other exactly, so one pull request moves both."""
    groups = {
        rule["groupName"]: set(rule["matchPackageNames"])
        for rule in renovate_config["packageRules"]
        if "groupName" in rule
    }

    assert {"pydantic", "pydantic-core"} <= groups["pydantic"]


def test_renovate_digest_pins_skip_the_release_age(
    renovate_config: dict[str, Any],
) -> None:
    """A digest has no release date, so the release age must not hold it."""
    digest_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if "pinDigest" in rule.get("matchUpdateTypes", [])
    ]

    assert [rule["minimumReleaseAge"] for rule in digest_rules] == [None]


def test_renovate_leaves_workflow_actions_to_humans(
    renovate_config: dict[str, Any],
) -> None:
    """Actions run with the repository token, so a human merges their updates."""
    action_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if rule.get("matchManagers") == ["github-actions"]
    ]

    assert [rule["automerge"] for rule in action_rules] == [False]


def test_renovate_leaves_pre_commit_hooks_to_humans(
    renovate_config: dict[str, Any],
) -> None:
    """Hooks execute downloaded code, so a human merges their updates."""
    hook_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if rule.get("matchManagers") == ["pre-commit"]
    ]

    assert [rule["automerge"] for rule in hook_rules] == [False]


def test_renovate_leaves_build_tooling_to_humans(
    renovate_config: dict[str, Any],
) -> None:
    """The build backend runs while the wheel is built, so a human merges it."""
    build_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if "setuptools" in rule.get("matchPackageNames", [])
    ]

    assert [rule["automerge"] for rule in build_rules] == [False]


def test_renovate_vulnerability_alerts_use_only_supported_options(
    renovate_config: dict[str, Any],
) -> None:
    """Renovate rejects package-rule-only options inside vulnerabilityAlerts."""
    assert "prPriority" not in renovate_config["vulnerabilityAlerts"]


def test_dependabot_version_updates_are_removed() -> None:
    """Dependabot only reports alerts; Renovate opens the update pull requests."""
    assert not (ROOT_DIR / ".github" / "dependabot.yml").exists()
