# VENDORED: keep identical in bot-obormot and audiodoc. Source of truth: audiodoc.
# Copyright (c) 2026 Nikolai Zelensky
"""Check Russian documents against their English twins."""

from __future__ import annotations

import re
from pathlib import Path

from scripts.docs_checks.markdown import display_path, markdown_files, without_code

_H2_RE = re.compile(r"^ {0,3}##(?!#)[ \t]+(.+?)[ \t]*#*[ \t]*$")


def _h2_headings(path: Path) -> list[str]:
    """Return the ordered H2 headings in a Markdown document."""
    text = without_code(path.read_text(encoding="utf-8"))
    return [
        match.group(1).strip()
        for line in text.splitlines()
        if (match := _H2_RE.match(line)) is not None
    ]


def _section_number(heading: str) -> str | None:
    """Return a numbered section prefix, if present."""
    match = re.match(r"^\s*(\d+(?:\.\d+)*)(?:[.)])?\s+", heading)
    return match.group(1) if match else None


def check_section_parity(root: Path) -> list[str]:
    """Check that Russian documents match their English twins structurally."""
    errors: list[str] = []

    for russian_path in markdown_files(root):
        if not russian_path.name.endswith(".ru.md"):
            continue

        english_path = Path(str(russian_path)[: -len(".ru.md")] + ".md")
        if not english_path.is_file():
            errors.append(f"{display_path(russian_path, root)}: missing English twin")
            continue

        english = _h2_headings(english_path)
        russian = _h2_headings(russian_path)

        if len(english) != len(russian):
            errors.append(
                f"{display_path(russian_path, root)}: H2 section count "
                f"differs from {display_path(english_path, root)} "
                f"({len(russian)} != {len(english)})"
            )
            continue

        english_numbers = [_section_number(heading) for heading in english]
        russian_numbers = [_section_number(heading) for heading in russian]

        if (any(english_numbers) or any(russian_numbers)) and (
            english_numbers != russian_numbers
        ):
            errors.append(
                f"{display_path(russian_path, root)}: H2 section order "
                f"differs from {display_path(english_path, root)}"
            )

    return errors


def check_russian_documents(root: Path) -> list[str]:
    """Ensure every Russian Markdown document contains Cyrillic characters."""
    return [
        f"{display_path(path, root)}: no Cyrillic characters"
        for path in markdown_files(root)
        if path.name.endswith(".ru.md")
        and re.search(
            r"[\u0400-\u04ff]",
            path.read_text(encoding="utf-8"),
        )
        is None
    ]
