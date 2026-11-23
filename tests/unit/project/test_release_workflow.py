# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for CI, release automation, vendored files and release metadata."""

import re
import tomllib
from pathlib import Path

from scripts.check_vendored import (
    HEADERLESS_VENDORED_FILES,
    PACKAGE_VENDORED_FILES,
    VENDORED_FILES,
    VENDORED_HEADER,
)

ROOT_DIR = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT_DIR / ".github" / "workflows"


def _job_names(name: str) -> set[str]:
    """Return the job identifiers declared in a workflow file."""
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    jobs_section = text.split("\njobs:\n", maxsplit=1)[1]
    return set(re.findall(r"(?m)^  ([a-z][a-z-]*):\s*$", jobs_section))


def test_ci_has_the_required_jobs() -> None:
    """The CI workflow has every job the release process depends on."""
    assert _job_names("ci.yml") == {
        "lint",
        "test",
        "integration",
        "audit",
        "build",
        "installer",
        "docker",
    }


def test_ci_jobs_call_make_targets() -> None:
    """Every job delegates its main work to a Makefile target."""
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")

    for target in (
        "make lint",
        "make types pylint deptry vulture import-lint",
        "make test",
        "make integration",
        "make audit",
        "make build",
        "make installer",
        "make docker",
    ):
        assert target in text, target


def test_makefile_defines_every_target_used_by_ci() -> None:
    """The Makefile declares all the targets CI calls."""
    makefile = (ROOT_DIR / "Makefile").read_text(encoding="utf-8")

    for target in (
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
        "check",
    ):
        assert re.search(rf"(?m)^{re.escape(target)}:", makefile), target
    expected_fragment = (
        "check: lint types pylint deptry vulture import-lint test docs-check"
    )
    assert expected_fragment in makefile


def test_installer_smoke_test_installs_locked_runtime_dependencies() -> None:
    """Installer smoke tests use the project's locked runtime dependencies."""
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    installer_step = text.split(
        "      - name: Install installer smoke-test tools\n", maxsplit=1
    )[1].split("\n      - name:", maxsplit=1)[0]

    expected_fragment = "--constraint requirements-lock.txt"
    assert expected_fragment in installer_step
    expected_fragment = "-r requirements.txt"
    assert expected_fragment in installer_step


def test_ci_build_job_verifies_release_assets_and_metadata() -> None:
    """The build job checks both distributions, checksums and the wheel."""
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")

    expected_fragment = "sdists=(dist/bot_obormot-*.tar.gz)"
    assert expected_fragment in text
    expected_fragment = "wheels=(dist/bot_obormot-*.whl)"
    assert expected_fragment in text
    expected_fragment = "sha256sum --check --status SHA256SUMS"
    assert expected_fragment in text
    expected_fragment = "twine check"
    assert expected_fragment in text
    expected_fragment = 'bot-obormot" version'
    assert expected_fragment in text


def test_ci_pins_every_third_party_action_to_a_commit() -> None:
    """Actions are referenced by a full commit SHA, never by a moving tag."""
    for workflow in WORKFLOWS.glob("*.yml"):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            match = re.search(r"uses:\s*(\S+)", line)
            if match is None or match.group(1).startswith(("./", "$/")):
                continue
            assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", match.group(1)), line


def test_reusable_workflow_references_are_valid() -> None:
    """Release workflows call CI through a valid self-repository workflow path."""
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
    for name in ("release.yml", "docker-publish.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        expected_fragment = "$/.github/workflows/ci.yml"
        assert expected_fragment in text
        assert pattern.search(text) or pattern_with_permissions_first.search(text), name


def test_workflows_contain_no_russian_text() -> None:
    """Workflow messages are English, like every other log message."""
    for workflow in WORKFLOWS.glob("*.yml"):
        assert re.search(r"[А-Яа-яЁё]", workflow.read_text(encoding="utf-8")) is None


def test_release_workflow_builds_and_publishes_the_release_assets() -> None:
    """The release workflow verifies assets, attests them and creates a draft."""
    text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")

    expected_fragment = "needs: ci"
    assert expected_fragment in text
    expected_fragment = "scripts/release_notes.py"
    assert expected_fragment in text
    expected_fragment = "scripts/build_release.sh"
    assert expected_fragment in text
    expected_fragment = "actions/attest@"
    assert expected_fragment in text
    expected_fragment = "--draft"
    assert expected_fragment in text
    expected_fragment = "--prerelease"
    assert expected_fragment in text
    expected_fragment = "dry_run"
    assert expected_fragment in text
    expected_fragment = "ghcr.io"
    assert expected_fragment in text


def test_headerless_vendored_files_exist() -> None:
    """Shared files without a header are present in the repository."""
    for relative_path in HEADERLESS_VENDORED_FILES:
        assert (ROOT_DIR / relative_path).is_file(), relative_path


def test_project_vendored_files_have_required_headers() -> None:
    """Every vendored file starts with the shared marker line."""
    for relative_path in VENDORED_FILES:
        first_line = (
            (ROOT_DIR / relative_path).read_text(encoding="utf-8").splitlines()[0]
        )
        assert first_line == VENDORED_HEADER, relative_path

    package_dir = ROOT_DIR / "bot_obormot"
    for filename in PACKAGE_VENDORED_FILES:
        first_line = (
            (package_dir / filename).read_text(encoding="utf-8").splitlines()[0]
        )
        assert first_line == VENDORED_HEADER, filename


def test_version_and_changelog_prepare_release_030() -> None:
    """Version 0.3.0 is current and documents its removals."""
    pyproject = tomllib.loads((ROOT_DIR / "pyproject.toml").read_text("utf-8"))
    changelog = (ROOT_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    release_entry = changelog.split("## [0.3.0] - ", maxsplit=1)[1].split(
        "\n## [", maxsplit=1
    )[0]

    expected_version = "0.3.0"
    assert pyproject["project"]["version"] == expected_version
    for section in ("### Added", "### Changed", "### Removed"):
        assert section in release_entry
    expected_fragment = "Deprecated functionality is not supported starting with 0.3.0."
    assert expected_fragment in release_entry


def test_changelog_keeps_the_release_022_entry() -> None:
    """Version 0.2.2 keeps its historical changelog entry."""
    changelog = (ROOT_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    release_entry = changelog.split("## [0.2.2] - ", maxsplit=1)[1].split(
        "\n## [", maxsplit=1
    )[0]

    for section in ("### Added", "### Fixed"):
        assert section in release_entry
    expected_fragment = "SYSTEM_PROMPT_PATH"
    assert expected_fragment in release_entry
    expected_fragment = "LLM_MAX_TOKENS"
    assert expected_fragment in release_entry
    expected_fragment = "LLMEmptyResponseError"
    assert expected_fragment in release_entry


def test_version_and_changelog_prepare_release_021() -> None:
    """Version 0.2.1 keeps its historical changelog entry and required sections."""
    changelog = (ROOT_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    release_entry = changelog.split("## [0.2.1] - ", maxsplit=1)[1].split(
        "\n## [", maxsplit=1
    )[0]

    for section in ("### Added", "### Changed"):
        assert section in release_entry
    expected_fragment = "reply_parameters"
    assert expected_fragment in release_entry
    expected_fragment = "parse_mode"
    assert expected_fragment in release_entry


def test_changelog_keeps_the_release_020_entry() -> None:
    """Version 0.2.0 keeps its changelog entry with the required sections."""
    changelog = (ROOT_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    release_entry = changelog.split("## [0.2.0] - ", maxsplit=1)[1].split(
        "\n## [", maxsplit=1
    )[0]

    for section in ("### Added", "### Changed", "### Deprecated", "### Removed"):
        assert section in release_entry
    expected_fragment = "WHISPER_"
    assert expected_fragment in release_entry
    expected_fragment = "python -m bot.main"
    assert expected_fragment in release_entry
    expected_fragment = "0.3.0"
    assert expected_fragment in release_entry
