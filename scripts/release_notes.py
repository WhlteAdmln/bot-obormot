# Copyright (c) 2026 Nikolai Zelensky
"""Extract release notes from the project changelog."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


class MissingReleaseEntryError(ValueError):
    """Raised when the requested release version is absent."""

    def __init__(self) -> None:
        """Initialize the exception with its default message."""
        super().__init__("Missing release entry.")


class EmptyReleaseEntryError(ValueError):
    """Raised when the requested release entry has no notes."""

    def __init__(self) -> None:
        """Initialize the exception with its default message."""
        super().__init__("Empty release entry.")


def extract_release_notes(changelog: str, version: str) -> str:
    """Extract the notes for one release version.

    Args:
        changelog: Full Keep a Changelog document.
        version: Release version without the leading ``v``.

    Returns:
        The release notes without the version heading.

    Raises:
        ValueError: If the version entry is missing or has no notes.
    """
    lines = changelog.splitlines()
    start: int | None = None

    for index, line in enumerate(lines):
        match = re.fullmatch(r"## \[([^\]]+)\](?:\s+-.*)?", line)
        if match is not None and match.group(1) == version:
            start = index + 1
            break

    if start is None:
        raise MissingReleaseEntryError

    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    notes = "\n".join(lines[start:end]).strip()
    if not notes:
        raise EmptyReleaseEntryError

    return f"{notes}\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Extract a version's changelog section into an output file.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Zero when the release notes were written successfully.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("changelog", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)

    try:
        notes = extract_release_notes(
            args.changelog.read_text(encoding="utf-8"),
            args.version,
        )
    except ValueError as error:
        parser.error(str(error))

    args.output.write_text(notes, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
