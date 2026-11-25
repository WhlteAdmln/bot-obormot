# VENDORED: keep identical in bot-obormot and audiodoc. Source of truth: audiodoc.
# Copyright (c) 2026 Nikolai Zelensky
"""Check that local Markdown links and their anchors exist."""

from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from scripts.docs_checks.markdown import display_path, markdown_files, without_code

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_SLUG_PUNCTUATION = "-_ "
_INLINE_LINK_RE = re.compile(r"!?\[[^\]]+\]\(\s*(?:<([^>]+)>|([^\s)]+))")
_REFERENCE_LINK_RE = re.compile(r"(?m)^\s*\[[^\]]+\]:\s*(?:<([^>]+)>|(\S+))")
_HTML_LINK_RE = re.compile(
    r"""\b(?:href|src)\s*=\s*(['"])(.*?)\1""",
    re.IGNORECASE,
)
_HTML_ID_RE = re.compile(
    r"""\b(?:id|name)\s*=\s*(['"])(.*?)\1""",
    re.IGNORECASE,
)


def _heading_slug(heading: str) -> str:
    """Convert a Markdown heading into a GitHub-style anchor."""
    heading = html.unescape(heading)
    heading = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", heading)
    heading = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading)
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = re.sub(r"[`*_~]", "", heading).lower()
    slug = "".join(
        character
        for character in heading
        if character.isalnum() or character in _SLUG_PUNCTUATION
    )
    return re.sub(r"\s+", "-", slug).strip("-")


def _anchor_names(path: Path) -> set[str]:
    """Collect heading and explicit HTML anchors from a document."""
    text = without_code(path.read_text(encoding="utf-8"))
    anchors: set[str] = set()
    counts: dict[str, int] = {}

    for line in text.splitlines():
        match = re.match(
            r"^ {0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$",
            line,
        )
        if match is None:
            continue

        slug = _heading_slug(match.group(1))
        if not slug:
            continue

        count = counts.get(slug, 0)
        anchors.add(slug if count == 0 else f"{slug}-{count}")
        counts[slug] = count + 1

    anchors.update(
        html.unescape(match.group(2)) for match in _HTML_ID_RE.finditer(text)
    )
    return anchors


def _link_targets(text: str) -> Iterator[tuple[str, int]]:
    """Extract Markdown and HTML link targets with their source lines."""
    cleaned = without_code(text)

    for pattern in (_INLINE_LINK_RE, _REFERENCE_LINK_RE):
        for match in pattern.finditer(cleaned):
            target = match.group(1) or match.group(2)
            line = cleaned.count("\n", 0, match.start()) + 1
            yield html.unescape(target), line

    for match in _HTML_LINK_RE.finditer(cleaned):
        line = cleaned.count("\n", 0, match.start()) + 1
        yield html.unescape(match.group(2)), line


def _check_link_target(
    source: Path,
    target: str,
    line_number: int,
    root: Path,
    anchor_cache: dict[Path, set[str]],
) -> str | None:
    """Return an error for a broken local link or anchor."""
    parsed = urlsplit(target)
    if parsed.scheme or target.startswith("//"):
        return None

    target_path = unquote(parsed.path)
    if not target_path:
        destination = source
    elif target_path.startswith("/"):
        destination = root / target_path.lstrip("/")
    else:
        destination = source.parent / target_path

    source_name = display_path(source, root)
    if not destination.exists():
        return f"{source_name}:{line_number}: broken link '{target}'"

    fragment = unquote(parsed.fragment)
    if fragment and destination.suffix.lower() in {".md", ".html", ".htm"}:
        if destination not in anchor_cache:
            anchor_cache[destination] = _anchor_names(destination)

        if fragment not in anchor_cache[destination]:
            destination_name = display_path(destination, root)
            return (
                f"{source_name}:{line_number}: missing anchor "
                f"'#{fragment}' in '{destination_name}'"
            )

    return None


def check_markdown_links(root: Path) -> list[str]:
    """Check local Markdown, HTML, and reference links and their anchors."""
    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}

    for source in markdown_files(root):
        text = source.read_text(encoding="utf-8")
        for target, line_number in _link_targets(text):
            error = _check_link_target(
                source,
                target,
                line_number,
                root,
                anchor_cache,
            )
            if error is not None:
                errors.append(error)

    return errors
