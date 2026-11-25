# VENDORED: keep identical in bot-obormot and audiodoc. Source of truth: audiodoc.
# Copyright (c) 2026 Nikolai Zelensky
"""Report the number of changed lines of a pull request; never fail on the size."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

LINE_LIMIT = 256
EXCLUDED_PATTERNS = ("requirements-lock.txt", "*.ru.md")
GENERATED_ATTRIBUTE = "linguist-generated"
_GENERATED_VALUES = frozenset({"set", "true"})
_BINARY_COUNT = "-"
_GIT = shutil.which("git") or "git"


def _git(repo: Path, *args: str, stdin: str = "") -> str:
    return subprocess.run(  # noqa: S603  # fixed git argv, shell=False
        [_GIT, *args],
        cwd=repo,
        input=stdin,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _changed_files(repo: Path, base: str) -> list[tuple[int, str]]:
    """Return changed lines and the new path of every file changed since the base."""
    fields = iter(_git(repo, "diff", "--numstat", "-z", f"{base}...HEAD").split("\0"))
    changes = []
    for field in fields:
        if not field:
            continue
        added, deleted, path = field.split("\t")
        if not path:
            next(fields)
            path = next(fields)
        lines = 0 if added == _BINARY_COUNT else int(added) + int(deleted)
        changes.append((lines, path))
    return changes


def _generated_paths(repo: Path, paths: list[str]) -> set[str]:
    output = _git(
        repo,
        "check-attr",
        "-z",
        "--stdin",
        GENERATED_ATTRIBUTE,
        stdin="\0".join(paths),
    )
    fields = output.split("\0")
    return {
        path
        for path, value in zip(fields[0::3], fields[2::3], strict=False)
        if value in _GENERATED_VALUES
    }


def count_changed_lines(repo: Path, base: str) -> int:
    """Count insertions plus deletions since the merge base, without excluded files."""
    changes = _changed_files(repo, base)
    generated = _generated_paths(repo, [path for _, path in changes])
    return sum(
        lines
        for lines, path in changes
        if path not in generated
        and not any(fnmatch(path, pattern) for pattern in EXCLUDED_PATTERNS)
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Print the pull request size and the limit; always exit with 0."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Git revision to compare with.")
    args = parser.parse_args(argv)
    try:
        lines = count_changed_lines(Path.cwd(), args.base)
    except subprocess.CalledProcessError as exc:
        sys.stdout.write(
            f"Cannot measure the pull request size: {exc.stderr.strip()}\n"
        )
        return 0
    excluded = ", ".join(EXCLUDED_PATTERNS)
    sys.stdout.write(
        f"Changed lines: {lines} (limit {LINE_LIMIT}; "
        f"not counted: {excluded} and {GENERATED_ATTRIBUTE} files)\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
