# VENDORED: keep identical in bot-obormot and audiodoc. Source of truth: audiodoc.
# Copyright (c) 2026 Nikolai Zelensky
"""Find Markdown documents and strip or extract their code."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

IGNORED_DIRECTORIES = frozenset(
    {".git", ".venv", "venv", "tmp", "dist", "build", "node_modules"}
)
FENCED_BLOCK_RE = re.compile(r"(?ms)^(`{3,}|~{3,})[^\n]*\n(.*?)^\1[ \t]*$")


def markdown_files(root: Path) -> list[Path]:
    """Return repository Markdown files outside generated directories."""
    return sorted(
        path
        for path in root.rglob("*.md")
        if not IGNORED_DIRECTORIES.intersection(path.relative_to(root).parts[:-1])
    )


def without_code(text: str) -> str:
    """Remove fenced and inline code while preserving line positions."""
    text = FENCED_BLOCK_RE.sub(
        lambda match: "\n" * match.group(0).count("\n"),
        text,
    )
    return re.sub(r"`+[^`\n]*`+", "", text)


def code_segments(text: str) -> list[str]:
    """Return fenced and inline code segments from Markdown."""
    blocks = list(FENCED_BLOCK_RE.finditer(text))
    segments = [match.group(2) for match in blocks]
    remainder = FENCED_BLOCK_RE.sub("", text)
    segments.extend(re.findall(r"`([^`\n]+)`", remainder))
    return segments


def display_path(path: Path, root: Path) -> str:
    """Return a project-relative path when possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
