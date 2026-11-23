# VENDORED: keep identical in bot-obormot and audiodoc. Source of truth: audiodoc.
# Copyright (c) 2026 Nikolai Zelensky
"""Check that changelog sections follow the project order."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG_FILE = "CHANGELOG.md"
# Keep a Changelog names, ordered as this project writes them.
SECTION_ORDER = ("Added", "Changed", "Deprecated", "Fixed", "Removed", "Security")
_VERSION_RE = re.compile(r"^## \[([^\]]+)\]")
_SECTION_RE = re.compile(r"^### (.+?)(?: \(.*\))?\s*$")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _check_version_sections(version: str, sections: list[str]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    previous: str | None = None
    for name in sections:
        if name not in SECTION_ORDER:
            expected = ", ".join(SECTION_ORDER)
            errors.append(
                f"{CHANGELOG_FILE}: [{version}]: unknown section '{name}'; "
                f"expected one of {expected}"
            )
            continue
        if name in seen:
            errors.append(f"{CHANGELOG_FILE}: [{version}]: duplicate section '{name}'")
            continue
        seen.add(name)
        if previous is not None and SECTION_ORDER.index(name) < SECTION_ORDER.index(
            previous
        ):
            errors.append(
                f"{CHANGELOG_FILE}: [{version}]: section '{name}' must come "
                f"before '{previous}'"
            )
            continue
        previous = name
    return errors


def check_changelog(root: Path = PROJECT_ROOT) -> list[str]:
    """Check the order of the ``###`` sections inside every changelog version.

    Sections may be omitted, but those that are present must follow
    ``SECTION_ORDER`` and appear once. A parenthesized suffix after the section
    name is ignored.

    Args:
        root: Repository root that contains ``CHANGELOG.md``.

    Returns:
        A list of error messages, empty when the changelog is valid.
    """
    path = root / CHANGELOG_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return [f"{CHANGELOG_FILE}: file not found"]

    versions: list[tuple[str, list[str]]] = []
    errors: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        fence_match = _FENCE_RE.match(line)
        if fence_match is not None:
            marker = fence_match.group(1)[0]
            fence = None if fence == marker else (fence or marker)
        elif fence is not None:
            continue
        elif (version_match := _VERSION_RE.match(line)) is not None:
            versions.append((version_match.group(1), []))
        elif (section_match := _SECTION_RE.match(line)) is not None:
            if versions:
                versions[-1][1].append(section_match.group(1).strip())
            else:
                errors.append(
                    f"{CHANGELOG_FILE}: section '{section_match.group(1).strip()}' "
                    "is outside a version"
                )

    for version, sections in versions:
        errors.extend(_check_version_sections(version, sections))
    return errors


def main() -> int:
    """Run the changelog check and print any failures."""
    errors = check_changelog()
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1

    sys.stdout.write("Changelog section order is valid.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
