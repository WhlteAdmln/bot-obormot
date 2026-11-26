# Copyright (c) 2026 Nikolai Zelensky
"""Check that repository paths in the inline code of documents exist."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from scripts.docs_checks.markdown import FENCED_BLOCK_RE, display_path

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_DOCUMENT_PATTERNS = ("README*.md", "CONTRIBUTING*.md", "docs/**/*.md")
_PATH_PREFIXES = ("bot_obormot/", "scripts/", "tests/")
_PLACEHOLDER = "<"
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")


def _documents(root: Path) -> list[Path]:
    """Return the documents whose code paths are checked."""
    return sorted(
        {path for pattern in _DOCUMENT_PATTERNS for path in root.glob(pattern)}
    )


def _code_paths(text: str) -> Iterator[tuple[int, str]]:
    """Yield repository paths from inline code with their line numbers."""
    text = FENCED_BLOCK_RE.sub(
        lambda match: "\n" * match.group(0).count("\n"),
        text,
    )
    for number, line in enumerate(text.splitlines(), start=1):
        for code in _INLINE_CODE_RE.findall(line):
            for segment in code.split():
                if segment.startswith(_PATH_PREFIXES) and _PLACEHOLDER not in segment:
                    yield number, segment.split("::", 1)[0]


def check_code_paths(root: Path) -> list[str]:
    """Report inline code paths of the documents that do not exist."""
    errors: list[str] = []
    for document in _documents(root):
        text = document.read_text(encoding="utf-8")
        errors.extend(
            f"{display_path(document, root)}:{number}: path not found: {path}"
            for number, path in _code_paths(text)
            if not (root / path).exists()
        )
    return errors
