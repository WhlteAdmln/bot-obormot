#!/usr/bin/env python3
"""Check that every direct runtime requirement is pinned compatibly in the lock."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version


def _read_requirements(path: Path) -> tuple[list[Requirement], list[str]]:
    requirements: list[Requirement] = []
    errors: list[str] = []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [f"Cannot read {path}: {exc}"]

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.split("#", maxsplit=1)[0].strip()
        if not line or line.startswith("-"):
            continue

        try:
            requirement = Requirement(line)
        except InvalidRequirement as exc:
            errors.append(f"{path}:{line_number}: invalid requirement {line!r}: {exc}")
            continue

        if requirement.url:
            errors.append(
                f"{path}:{line_number}: direct URL requirements are not supported: "
                f"{line}"
            )
            continue

        if requirement.marker and not requirement.marker.evaluate():
            continue

        requirements.append(requirement)

    return requirements, errors


def _read_lock(path: Path) -> tuple[dict[str, Version], list[str]]:
    locked: dict[str, Version] = {}
    errors: list[str] = []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {}, [f"Cannot read {path}: {exc}"]

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.split("#", maxsplit=1)[0].strip()
        if not line or line.startswith("-"):
            continue

        try:
            requirement = Requirement(line)
        except InvalidRequirement as exc:
            errors.append(f"{path}:{line_number}: invalid lock entry {line!r}: {exc}")
            continue

        specifiers = list(requirement.specifier)
        if (
            len(specifiers) != 1
            or specifiers[0].operator != "=="
            or "*" in specifiers[0].version
        ):
            errors.append(
                f"{path}:{line_number}: lock entry must use one exact == version: "
                f"{line}"
            )
            continue

        name = canonicalize_name(requirement.name)
        try:
            version = Version(specifiers[0].version)
        except InvalidVersion as exc:
            errors.append(f"{path}:{line_number}: invalid locked version: {exc}")
            continue

        if name in locked:
            errors.append(f"{path}:{line_number}: duplicate lock entry for {name}")
            continue
        locked[name] = version

    return locked, errors


def check_lock(requirements_path: Path, lock_path: Path) -> list[str]:
    """Return consistency errors; an empty list means the lock is valid."""
    requirements, errors = _read_requirements(requirements_path)
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
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", type=Path, default=root / "requirements.txt")
    parser.add_argument("--lock", type=Path, default=root / "requirements-lock.txt")
    args = parser.parse_args()

    errors = check_lock(args.requirements, args.lock)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Lock is consistent: {args.requirements} -> {args.lock}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
