# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the dependency update automation policy."""

import json
from pathlib import Path
from typing import Any

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]


@pytest.fixture(name="renovate_config")
def renovate_config_fixture() -> dict[str, Any]:
    """Load the Renovate configuration without its full-line comments."""
    lines = (ROOT_DIR / ".github" / "renovate.json5").read_text("utf-8").splitlines()
    text = "\n".join(line for line in lines if not line.lstrip().startswith("//"))
    config: dict[str, Any] = json.loads(text)
    return config


def test_renovate_extends_best_practices(renovate_config: dict[str, Any]) -> None:
    preset_name = "config:best-practices"
    assert preset_name in renovate_config["extends"], "best practices are not extended"


def test_renovate_merges_pull_requests_itself(
    renovate_config: dict[str, Any],
) -> None:
    assert renovate_config["automerge"] is True, "Renovate does not merge by itself"


def test_renovate_does_not_use_platform_automerge(
    renovate_config: dict[str, Any],
) -> None:
    assert renovate_config["platformAutomerge"] is False, "platform automerge is on"


def test_renovate_waits_for_status_checks(renovate_config: dict[str, Any]) -> None:
    assert renovate_config["ignoreTests"] is False, "Renovate ignores status checks"


def test_renovate_requires_fourteen_day_old_releases(
    renovate_config: dict[str, Any],
) -> None:
    expected_minimumreleaseage = "14 days"
    assert renovate_config["minimumReleaseAge"] == expected_minimumreleaseage, (
        "the minimum release age is not fourteen days"
    )


def test_renovate_security_fixes_skip_the_release_age(
    renovate_config: dict[str, Any],
) -> None:
    assert renovate_config["vulnerabilityAlerts"]["minimumReleaseAge"] is None, (
        "security fixes wait for the release age"
    )


def test_renovate_never_automerges_major_updates(
    renovate_config: dict[str, Any],
) -> None:
    major_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if rule.get("matchUpdateTypes") == ["major"]
    ]

    expected_flags = [False]
    assert [rule["automerge"] for rule in major_rules] == expected_flags, (
        "major updates are merged automatically"
    )


def test_renovate_generic_lock_maintenance_is_off(
    renovate_config: dict[str, Any],
) -> None:
    assert renovate_config["lockFileMaintenance"]["enabled"] is False, (
        "generic lock maintenance is on"
    )


def test_renovate_lock_refresh_runs_monthly(
    renovate_config: dict[str, Any],
) -> None:
    refresh_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if rule.get("matchUpdateTypes") == ["lockFileMaintenance"]
    ]

    expected_schedules = [["before 6am on the first day of the month"]]
    assert [rule["schedule"] for rule in refresh_rules] == expected_schedules, (
        "the lock refresh does not run monthly"
    )


def test_renovate_lock_refresh_rule_blocks_automerge(
    renovate_config: dict[str, Any],
) -> None:
    refresh_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if rule.get("matchUpdateTypes") == ["lockFileMaintenance"]
    ]

    expected_flags = [False]
    assert [rule["automerge"] for rule in refresh_rules] == expected_flags, (
        "the lock refresh is merged automatically"
    )


def test_renovate_regenerates_the_lock_with_pip_compile(
    renovate_config: dict[str, Any],
) -> None:
    manager_name = "pip-compile"
    assert manager_name in renovate_config["enabledManagers"], "pip-compile is off"


def test_renovate_does_not_edit_the_lock_line_by_line(
    renovate_config: dict[str, Any],
) -> None:
    manager_name = "pip_requirements"
    assert manager_name not in renovate_config["enabledManagers"], (
        "the lock is edited line by line"
    )


def test_renovate_python_version_changes_are_left_to_humans(
    renovate_config: dict[str, Any],
) -> None:
    python_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if rule.get("matchDepNames") == ["python"]
    ]

    expected_flags = [False]
    assert [rule["enabled"] for rule in python_rules] == expected_flags, (
        "Python version updates are enabled"
    )


def test_lock_command_writes_options_with_equal_signs() -> None:
    makefile = (ROOT_DIR / "Makefile").read_text("utf-8")

    python_option = "--python-version=$(LOCK_PYTHON_VERSION)"
    assert python_option in makefile, "the Python version option has no equal sign"


def test_lock_command_names_the_output_file_with_an_equal_sign() -> None:
    makefile = (ROOT_DIR / "Makefile").read_text("utf-8")

    output_option = "--output-file=requirements-lock.txt"
    assert output_option in makefile, "the output file option has no equal sign"


def test_renovate_updates_pydantic_and_its_core_together(
    renovate_config: dict[str, Any],
) -> None:
    group_key = "groupName"
    groups = {
        rule["groupName"]: set(rule["matchPackageNames"])
        for rule in renovate_config["packageRules"]
        if group_key in rule
    }

    expected_packages = {"pydantic", "pydantic-core"}
    assert expected_packages <= groups["pydantic"], (
        "pydantic and its core are not grouped"
    )


def test_renovate_digest_pins_skip_the_release_age(
    renovate_config: dict[str, Any],
) -> None:
    digest_key = "pinDigest"
    digest_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if digest_key in rule.get("matchUpdateTypes", [])
    ]

    expected_ages = [None]
    assert [rule["minimumReleaseAge"] for rule in digest_rules] == expected_ages, (
        "digest pins wait for the release age"
    )


def test_renovate_leaves_workflow_actions_to_humans(
    renovate_config: dict[str, Any],
) -> None:
    action_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if rule.get("matchManagers") == ["github-actions"]
    ]

    expected_flags = [False]
    assert [rule["automerge"] for rule in action_rules] == expected_flags, (
        "workflow actions are merged automatically"
    )


def test_renovate_leaves_pre_commit_hooks_to_humans(
    renovate_config: dict[str, Any],
) -> None:
    hook_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if rule.get("matchManagers") == ["pre-commit"]
    ]

    expected_flags = [False]
    assert [rule["automerge"] for rule in hook_rules] == expected_flags, (
        "pre-commit hooks are merged automatically"
    )


def test_renovate_leaves_build_tooling_to_humans(
    renovate_config: dict[str, Any],
) -> None:
    package_name = "setuptools"
    build_rules = [
        rule
        for rule in renovate_config["packageRules"]
        if package_name in rule.get("matchPackageNames", [])
    ]

    expected_flags = [False]
    assert [rule["automerge"] for rule in build_rules] == expected_flags, (
        "build tooling is merged automatically"
    )


def test_renovate_vulnerability_alerts_use_only_supported_options(
    renovate_config: dict[str, Any],
) -> None:
    priority_key = "prPriority"
    assert priority_key not in renovate_config["vulnerabilityAlerts"], (
        "vulnerability alerts use the unsupported prPriority option"
    )


def test_dependabot_version_updates_are_removed() -> None:
    dependabot_path = ROOT_DIR / ".github" / "dependabot.yml"
    assert dependabot_path.exists() is False, "the Dependabot configuration is back"
