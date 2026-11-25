# VENDORED: keep identical in bot-obormot and audiodoc. Source of truth: audiodoc.
# Copyright (c) 2026 Nikolai Zelensky
"""Check that files shared with bot-obormot are identical."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_VENDORED_HEADER_PREFIX = "# VENDORED: keep identical in bot-obormot and audiodoc."
VENDORED_HEADER = f"{_VENDORED_HEADER_PREFIX} Source of truth: audiodoc."
PYPROJECT_FILE = "pyproject.toml"
# The Makefile and the CI workflow are intentionally not shared: they run
# project-specific jobs (OCR and Whisper for audiodoc, Telegram for the bot).
VENDORED_FILES = (
    ".editorconfig",
    ".pre-commit-config.yaml",
    "scripts/check_changelog.py",
    "scripts/check_lock.py",
    "scripts/check_test_layout.py",
    "scripts/check_test_rules.py",
    "scripts/check_vendored.py",
    "scripts/coverage_gaps.py",
    "scripts/report_pr_size.py",
    PYPROJECT_FILE,
    ".markdownlint-cli2.yaml",
)
# These files cannot carry the header: a shebang must stay on the first line,
# Markdown would render it as a heading and JSON5 has no `#` comments.
HEADERLESS_VENDORED_FILES = (
    ".github/renovate.json5",
    "AGENTS.md",
    "CLAUDE.md",
    "docs/development-principles.md",
    "docs/development-principles.ru.md",
    "scripts/build_release.sh",
    "tests/unit/scripts/test_check_changelog.py",
    "tests/unit/scripts/test_check_test_rules.py",
    "tests/unit/scripts/test_report_pr_size.py",
)
PACKAGE_VENDORED_FILES = ("log_filters.py", "env_readers.py")
# Only style and typing rules are shared. The dependency, dead-code and import
# contract tables describe each project's own structure and must differ.
LINT_TOOL_NAMES = ("ruff", "mypy", "pylint")


def _read_vendored_file(
    path: Path,
    errors: list[str],
    *,
    require_header: bool = True,
) -> bytes | None:
    try:
        content = path.read_bytes()
    except FileNotFoundError:
        errors.append(f"{path}: file not found")
        return None
    except OSError as error:
        errors.append(f"{path}: cannot read file: {error}")
        return None

    if require_header and content.splitlines()[:1] != [VENDORED_HEADER.encode("utf-8")]:
        errors.append(f"{path}: missing VENDORED header")
    return content


def _normalize_package_references(
    value: object,
    pattern: re.Pattern[str],
) -> object:
    if isinstance(value, str):
        return pattern.sub("<package>", value)
    if isinstance(value, list):
        return [_normalize_package_references(item, pattern) for item in value]
    if isinstance(value, dict):
        return {
            key: _normalize_package_references(item, pattern)
            for key, item in value.items()
        }
    return value


def _lint_configuration_hash(
    content: bytes,
    path: Path,
    package_name: str | None,
    errors: list[str],
) -> str | None:
    try:
        project_data = tomllib.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        errors.append(f"{path}: invalid TOML: {error}")
        return None

    tool_data = project_data.get("tool")
    if not isinstance(tool_data, dict):
        errors.append(f"{path}: missing [tool] table")
        return None
    if package_name is None:
        errors.append(f"{path}: cannot identify package for lint comparison")
        return None

    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(package_name)}(?![A-Za-z0-9_])")
    lint_blocks: dict[str, object] = {}
    for tool_name in LINT_TOOL_NAMES:
        if tool_name not in tool_data:
            continue
        block = tool_data[tool_name]
        if not isinstance(block, dict):
            errors.append(f"{path}: [tool.{tool_name}] must be a table")
            return None
        lint_blocks[tool_name] = _normalize_package_references(block, pattern)

    serialized = json.dumps(
        lint_blocks,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _content_hash(
    content: bytes,
    path: Path,
    package_name: str | None,
    errors: list[str],
) -> str | None:
    if path.name == PYPROJECT_FILE:
        return _lint_configuration_hash(content, path, package_name, errors)

    return hashlib.sha256(content).hexdigest()


def _compare_files(
    local_path: Path,
    other_path: Path,
    label: str,
    errors: list[str],
    package_names: tuple[str | None, str | None],
    *,
    require_header: bool = True,
) -> None:
    local_package, other_package = package_names
    local_content = _read_vendored_file(
        local_path, errors, require_header=require_header
    )
    other_content = _read_vendored_file(
        other_path, errors, require_header=require_header
    )
    if local_content is None or other_content is None:
        return

    local_hash = _content_hash(local_content, local_path, local_package, errors)
    other_hash = _content_hash(other_content, other_path, other_package, errors)
    if local_hash is None or other_hash is None or local_hash == other_hash:
        return

    if label == PYPROJECT_FILE:
        errors.append(f"{label}: lint configuration differs from other repository")
    else:
        errors.append(f"{label}: content differs from other repository")


def _find_package_dir(
    root: Path,
    repository: str,
    errors: list[str],
) -> Path | None:
    package_files = root.glob("*/log_filters.py")
    matches = sorted(path.parent for path in package_files if path.is_file())
    if len(matches) != 1:
        errors.append(
            f"{repository}: expected exactly one package containing log_filters.py, "
            f"found {len(matches)}"
        )
        return None
    return matches[0]


def check_vendored(other: Path, root: Path = PROJECT_ROOT) -> list[str]:
    """Return differences between this repository and another repository.

    Args:
        other: Path to the other repository.
        root: Repository root to check. Defaults to this project.

    Returns:
        A list of missing files, invalid headers, or content differences.
    """
    local_root = root.resolve()
    other_root = other.resolve()
    errors: list[str] = []
    if not local_root.is_dir():
        return [f"Local repository does not exist: {local_root}"]
    if not other_root.is_dir():
        return [f"Other repository does not exist: {other_root}"]

    local_package = _find_package_dir(local_root, "local repository", errors)
    other_package = _find_package_dir(other_root, "other repository", errors)

    for relative_path in VENDORED_FILES:
        local_path = local_root / relative_path
        other_path = other_root / relative_path
        if relative_path == PYPROJECT_FILE and (
            local_package is None or other_package is None
        ):
            _read_vendored_file(local_path, errors)
            _read_vendored_file(other_path, errors)
            continue
        _compare_files(
            local_path,
            other_path,
            relative_path,
            errors,
            (
                local_package.name if local_package is not None else None,
                other_package.name if other_package is not None else None,
            ),
        )

    for relative_path in HEADERLESS_VENDORED_FILES:
        _compare_files(
            local_root / relative_path,
            other_root / relative_path,
            relative_path,
            errors,
            (None, None),
            require_header=False,
        )

    if local_package is not None and other_package is not None:
        for filename in PACKAGE_VENDORED_FILES:
            _compare_files(
                local_package / filename,
                other_package / filename,
                f"<package>/{filename}",
                errors,
                (local_package.name, other_package.name),
            )

    return errors


def main(argv: Sequence[str] | None = None) -> int:
    """Run the vendored-file consistency check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--other",
        type=Path,
        required=True,
        help="Path to the other repository",
    )
    args = parser.parse_args(argv)
    errors = check_vendored(args.other)
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1

    file_count = (
        len(VENDORED_FILES)
        + len(HEADERLESS_VENDORED_FILES)
        + len(PACKAGE_VENDORED_FILES)
    )
    sys.stdout.write(f"Vendored files match: {file_count} files.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
