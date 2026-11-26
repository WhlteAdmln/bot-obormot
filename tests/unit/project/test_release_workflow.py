# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for CI, release automation, vendored files and release metadata."""

import re
import tomllib
from pathlib import Path

import pytest

from scripts.check_vendored import (
    HEADERLESS_VENDORED_FILES,
    PACKAGE_VENDORED_FILES,
    VENDORED_FILES,
    VENDORED_HEADER,
)

ROOT_DIR = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT_DIR / ".github" / "workflows"


def _workflow_text(name: str) -> str:
    """Return the text of one workflow file."""
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _job_names(name: str) -> set[str]:
    """Return the job identifiers declared in a workflow file."""
    jobs_section = _workflow_text(name).split("\njobs:\n", maxsplit=1)[1]
    return set(re.findall(r"(?m)^  ([a-z][a-z-]*):\s*$", jobs_section))


def _installer_step() -> str:
    """Return the CI step that installs the installer smoke-test tools."""
    text = _workflow_text("ci.yml")
    return text.split("      - name: Install installer smoke-test tools\n", maxsplit=1)[
        1
    ].split("\n      - name:", maxsplit=1)[0]


def _release_entry(version: str) -> str:
    """Return the changelog section of one release."""
    changelog = (ROOT_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    return changelog.split(f"## [{version}] - ", maxsplit=1)[1].split(
        "\n## [", maxsplit=1
    )[0]


def _first_line(path: Path) -> str:
    """Return the first line of a text file."""
    return path.read_text(encoding="utf-8").splitlines()[0]


def test_ci_declares_the_required_jobs() -> None:
    expected_jobs = {
        "lint",
        "test",
        "integration",
        "pr-size",
        "audit",
        "build",
        "installer",
        "docker",
    }
    assert _job_names("ci.yml") == expected_jobs, "the CI jobs differ"


@pytest.mark.parametrize(
    "target",
    [
        "make lint",
        "make types pylint deptry vulture import-lint",
        "make test",
        "make integration",
        "make audit",
        "make build",
        "make installer",
        "make docker",
    ],
)
def test_ci_jobs_call_make_target(target: str) -> None:
    text = _workflow_text("ci.yml")
    assert target in text, f"the CI workflow does not run {target}"


@pytest.mark.parametrize(
    "target",
    [
        "lint",
        "types",
        "pylint",
        "deptry",
        "vulture",
        "import-lint",
        "test",
        "integration",
        "audit",
        "build",
        "installer",
        "docker",
        "docs-check",
        "pip-check",
        "test-no-skips",
        "release-check",
        "check",
    ],
)
def test_makefile_defines_target_used_by_ci(target: str) -> None:
    makefile = (ROOT_DIR / "Makefile").read_text(encoding="utf-8")
    found = re.search(rf"(?m)^{re.escape(target)}:", makefile) is not None
    assert found, f"the Makefile must define the {target} target"


def test_check_target_runs_every_local_ci_gate() -> None:
    makefile = (ROOT_DIR / "Makefile").read_text(encoding="utf-8")
    joined = makefile.replace("\\\n", " ")
    check_line = next(line for line in joined.splitlines() if line.startswith("check:"))
    gates = check_line.removeprefix("check:").split()
    expected_gates = [
        "lint",
        "types",
        "pylint",
        "deptry",
        "vulture",
        "import-lint",
        "pip-check",
        "test-no-skips",
        "audit",
        "release-check",
        "docs-check",
    ]
    assert gates == expected_gates, "make check must run every local CI gate"


@pytest.mark.parametrize(
    "option",
    ["--constraint requirements-lock.txt", "-r requirements.txt"],
)
def test_installer_smoke_test_installs_locked_runtime_dependencies(
    option: str,
) -> None:
    installer_step = _installer_step()
    assert option in installer_step, f"the installer smoke test lacks {option}"


@pytest.mark.parametrize(
    "snippet",
    [
        "sdists=(dist/bot_obormot-*.tar.gz)",
        "wheels=(dist/bot_obormot-*.whl)",
        "sha256sum --check --status SHA256SUMS",
        "twine check",
        'bot-obormot" version',
    ],
)
def test_ci_build_job_verifies_release_assets_and_metadata(snippet: str) -> None:
    text = _workflow_text("ci.yml")
    assert snippet in text, f"the CI build job does not contain {snippet}"


def test_ci_pins_every_third_party_action_to_a_commit() -> None:
    unpinned = [
        line
        for workflow in (
            *sorted(WORKFLOWS.glob("*.yml")),
            *sorted((ROOT_DIR / ".github" / "actions").glob("*/action.yml")),
        )
        for line in workflow.read_text(encoding="utf-8").splitlines()
        if (match := re.search(r"uses:\s*(\S+)", line)) is not None
        and not match.group(1).startswith(("./", "$/"))
        and re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", match.group(1)) is None
    ]
    expected_empty: list[str] = []
    assert unpinned == expected_empty, "some actions are not pinned to a commit"


def test_ci_installs_system_packages_only_through_the_shared_action() -> None:
    text = _workflow_text("ci.yml")
    direct_apt = "apt-get"
    assert direct_apt not in text, "a CI job installs system packages directly"


@pytest.mark.parametrize(
    "snippet",
    [
        "schedule:",
        "workflow_dispatch:",
        "--download-only",
        "actions/cache/save@",
        "hashFiles('.github/apt-packages.txt')",
    ],
)
def test_apt_cache_workflow_saves_the_package_files_nightly(snippet: str) -> None:
    text = _workflow_text("apt-cache.yml")
    assert snippet in text, f"the apt cache workflow does not contain {snippet}"


@pytest.mark.parametrize("name", ["release.yml", "docker-publish.yml"])
def test_reusable_workflow_references_the_ci_workflow(name: str) -> None:
    workflow_path = "$/.github/workflows/ci.yml"
    text = _workflow_text(name)
    assert workflow_path in text, f"{name} does not call the CI workflow"


@pytest.mark.parametrize("name", ["release.yml", "docker-publish.yml"])
def test_reusable_workflow_grants_the_ci_job_its_permissions(name: str) -> None:
    pattern = re.compile(
        r"(?m)^  ci:\n"
        r"(?:    name: .*\n)?"
        r"(?:    uses: \$/.github/workflows/ci\.yml\n)"
        r"    permissions:\n      contents: read\n      packages: write\n"
    )
    pattern_with_permissions_first = re.compile(
        r"(?m)^  ci:\n(?:    name: .*\n)?"
        r"    permissions:\n      contents: read\n      packages: write\n"
        r"    uses: \$/.github/workflows/ci\.yml\n"
    )
    text = _workflow_text(name)
    found = bool(pattern.search(text) or pattern_with_permissions_first.search(text))
    assert found, f"{name} does not declare the ci job with its permissions"


def test_workflows_contain_no_russian_text() -> None:
    russian = [
        workflow.name
        for workflow in sorted(WORKFLOWS.glob("*.yml"))
        if re.search(r"[А-Яа-яЁё]", workflow.read_text(encoding="utf-8"))
    ]
    expected_empty: list[str] = []
    assert russian == expected_empty, "some workflows contain Russian text"


@pytest.mark.parametrize(
    "snippet",
    [
        "needs: ci",
        "scripts/release_notes.py",
        "scripts/build_release.sh",
        "actions/attest@",
        "--draft",
        "--prerelease",
        "dry_run",
        "ghcr.io",
    ],
)
def test_release_workflow_builds_and_publishes_the_release_assets(
    snippet: str,
) -> None:
    text = _workflow_text("release.yml")
    assert snippet in text, f"the release workflow does not contain {snippet}"


def test_headerless_vendored_files_exist() -> None:
    missing = [
        relative_path
        for relative_path in HEADERLESS_VENDORED_FILES
        if not (ROOT_DIR / relative_path).is_file()
    ]
    expected_empty: list[str] = []
    assert missing == expected_empty, "some headerless vendored files are missing"


def test_project_vendored_files_have_required_headers() -> None:
    without_header = [
        relative_path
        for relative_path in VENDORED_FILES
        if _first_line(ROOT_DIR / relative_path) != VENDORED_HEADER
    ]
    expected_empty: list[str] = []
    assert without_header == expected_empty, "some vendored files lack the header"


def test_package_vendored_files_have_required_headers() -> None:
    package_dir = ROOT_DIR / "bot_obormot"
    without_header = [
        filename
        for filename in PACKAGE_VENDORED_FILES
        if _first_line(package_dir / filename) != VENDORED_HEADER
    ]
    expected_empty: list[str] = []
    assert without_header == expected_empty, "some package files lack the header"


def test_version_prepares_release_030() -> None:
    pyproject = tomllib.loads((ROOT_DIR / "pyproject.toml").read_text("utf-8"))
    expected_version = "0.3.0"
    version = pyproject["project"]["version"]
    assert version == expected_version, "the project version is not 0.3.0"


@pytest.mark.parametrize(
    ("version", "snippet"),
    [
        ("0.3.0", "### Added"),
        ("0.3.0", "### Changed"),
        ("0.3.0", "### Removed"),
        ("0.3.0", "Deprecated functionality is not supported starting with 0.3.0."),
        ("0.2.2", "### Added"),
        ("0.2.2", "### Fixed"),
        ("0.2.2", "SYSTEM_PROMPT_PATH"),
        ("0.2.2", "LLM_MAX_TOKENS"),
        ("0.2.2", "LLMEmptyResponseError"),
        ("0.2.1", "### Added"),
        ("0.2.1", "### Changed"),
        ("0.2.1", "reply_parameters"),
        ("0.2.1", "parse_mode"),
        ("0.2.0", "### Added"),
        ("0.2.0", "### Changed"),
        ("0.2.0", "### Deprecated"),
        ("0.2.0", "### Removed"),
        ("0.2.0", "WHISPER_"),
        ("0.2.0", "python -m bot.main"),
        ("0.2.0", "0.3.0"),
    ],
)
def test_changelog_release_entry_mentions(version: str, snippet: str) -> None:
    release_entry = _release_entry(version)
    assert snippet in release_entry, f"the {version} entry lacks {snippet}"
