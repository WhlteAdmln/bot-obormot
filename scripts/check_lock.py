# VENDORED: keep identical in bot-obormot and audiodoc. Source of truth: audiodoc.
# Copyright (c) 2026 Nikolai Zelensky
"""Check that every direct runtime requirement is pinned compatibly in the lock."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

_EXACT_OPERATOR = "=="
_WILDCARD = "*"


def _load_dependency_entries(path: Path) -> tuple[list[object], str | None]:
    """Return the raw [project].dependencies entries or the reason they are unusable."""
    try:
        project_data = tomllib.loads(path.read_text(encoding="utf-8")).get("project")
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [], f"Cannot read {path}: {exc}"

    if not isinstance(project_data, dict):
        return [], f"{path}: missing [project] table"

    raw_requirements = project_data.get("dependencies")
    if not isinstance(raw_requirements, list):
        return [], f"{path}: [project].dependencies must be an array"

    return raw_requirements, None


def _parse_project_requirement(
    path: Path, line_number: int, raw_requirement: object
) -> tuple[Requirement | None, str | None]:
    """Parse one dependency; return no requirement when it is skipped or invalid."""
    if not isinstance(raw_requirement, str):
        return None, (
            f"{path}: [project].dependencies entry {line_number} must be a string"
        )

    line = raw_requirement.strip()
    try:
        requirement = Requirement(line)
    except InvalidRequirement as exc:
        return None, (
            f"{path}: [project].dependencies entry {line_number}: "
            f"invalid requirement {line!r}: {exc}"
        )

    if requirement.url:
        return None, (
            f"{path}: [project].dependencies entry {line_number}: "
            f"direct URL requirements are not supported: {line}"
        )

    if requirement.marker and not requirement.marker.evaluate():
        return None, None

    return requirement, None


def _read_project_dependencies(path: Path) -> tuple[list[Requirement], list[str]]:
    raw_requirements, load_error = _load_dependency_entries(path)
    if load_error is not None:
        return [], [load_error]

    requirements: list[Requirement] = []
    errors: list[str] = []
    for line_number, raw_requirement in enumerate(raw_requirements, start=1):
        requirement, error = _parse_project_requirement(
            path, line_number, raw_requirement
        )
        if error is not None:
            errors.append(error)
        elif requirement is not None:
            requirements.append(requirement)

    return requirements, errors


def _parse_lock_entry(
    path: Path, line_number: int, line: str
) -> tuple[tuple[str, Version] | None, str | None]:
    """Parse one lock line into a canonical name and an exact version."""
    try:
        requirement = Requirement(line)
    except InvalidRequirement as exc:
        return None, f"{path}:{line_number}: invalid lock entry {line!r}: {exc}"

    specifiers = list(requirement.specifier)
    if (
        len(specifiers) != 1
        or specifiers[0].operator != _EXACT_OPERATOR
        or _WILDCARD in specifiers[0].version
    ):
        return None, (
            f"{path}:{line_number}: lock entry must use one exact == version: {line}"
        )

    try:
        version = Version(specifiers[0].version)
    except InvalidVersion as exc:
        return None, f"{path}:{line_number}: invalid locked version: {exc}"

    return (canonicalize_name(requirement.name), version), None


def _read_lock(path: Path) -> tuple[dict[str, Version], list[str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {}, [f"Cannot read {path}: {exc}"]

    locked: dict[str, Version] = {}
    errors: list[str] = []
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.split("#", maxsplit=1)[0].strip()
        if not line or line.startswith("-"):
            continue

        entry, error = _parse_lock_entry(path, line_number, line)
        if error is not None:
            errors.append(error)
        elif entry is not None:
            name, version = entry
            if name in locked:
                errors.append(f"{path}:{line_number}: duplicate lock entry for {name}")
            else:
                locked[name] = version

    return locked, errors


def check_lock(project_path: Path, lock_path: Path) -> list[str]:
    """Return consistency errors; an empty list means the lock is valid."""
    requirements, errors = _read_project_dependencies(project_path)
    locked, lock_errors = _read_lock(lock_path)
    errors.extend(lock_errors)

    for requirement in requirements:
        name = canonicalize_name(requirement.name)
        locked_version = locked.get(name)
        if locked_version is None:
            errors.append(f"Missing from lock file: {requirement.name}")
            continue
        if requirement.specifier and locked_version not in requirement.specifier:
            errors.append(
                f"Locked {requirement.name}=={locked_version} does not satisfy "
                f"{requirement.specifier}"
            )

    return errors


def main() -> int:
    """Run the lock consistency check."""
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=root / "pyproject.toml")
    parser.add_argument("--lock", type=Path, default=root / "requirements-lock.txt")
    args = parser.parse_args()

    errors = check_lock(args.project, args.lock)
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1

    sys.stdout.write(f"Lock is consistent: {args.project} -> {args.lock}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
