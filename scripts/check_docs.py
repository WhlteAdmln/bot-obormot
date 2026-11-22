# Copyright (c) 2026 Nikolai Zelensky
"""Check documentation links and consistency with application sources."""

from __future__ import annotations

import html
import re
import shlex
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import fields
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

if TYPE_CHECKING:
    from collections.abc import Iterator

from bot_obormot.cli import build_parser
from bot_obormot.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_IGNORED_DIRECTORIES = frozenset(
    {".git", ".venv", "venv", "tmp", "dist", "build", "node_modules"}
)

# Settings fields that are computed defaults and not environment variables.
_NON_ENVIRONMENT_FIELDS = frozenset(
    {"DEFAULT_HISTORY_EXCHANGES", "DEFAULT_SYSTEM_PROMPT"}
)

# Names documented in docs/configuration.md that are not Settings fields.
DOCUMENTATION_ONLY_ENV_NAMES = frozenset(
    {
        "BOT_OBORMOT_HOME",
    }
)

_COMMAND_DECLARATION_RE = re.compile(r"Command\(\"([a-z_]+)\"")

_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
_FENCED_BLOCK_RE = re.compile(r"(?ms)^(`{3,}|~{3,})[^\n]*\n(.*?)^\1[ \t]*$")
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
_ENV_ASSIGNMENT_LINE_RE = re.compile(r"(?m)^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=")
_CONFIG_SETTING_RE = re.compile(r"(?m)^\s*\|\s*`([A-Z][A-Z0-9_]*)`")
_H2_RE = re.compile(r"^ {0,3}##(?!#)[ \t]+(.+?)[ \t]*#*[ \t]*$")


def _markdown_files(root: Path) -> list[Path]:
    """Return repository Markdown files outside generated directories."""
    return sorted(
        path
        for path in root.rglob("*.md")
        if not _IGNORED_DIRECTORIES.intersection(path.relative_to(root).parts[:-1])
    )


def _without_code(text: str) -> str:
    """Remove fenced and inline code while preserving line positions."""
    text = _FENCED_BLOCK_RE.sub(
        lambda match: "\n" * match.group(0).count("\n"),
        text,
    )
    return re.sub(r"`+[^`\n]*`+", "", text)


def _heading_slug(heading: str) -> str:
    """Convert a Markdown heading into a GitHub-style anchor."""
    heading = html.unescape(heading)
    heading = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", heading)
    heading = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading)
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = re.sub(r"[`*_~]", "", heading).lower()
    slug = "".join(
        character for character in heading if character.isalnum() or character in "-_ "
    )
    return re.sub(r"\s+", "-", slug).strip("-")


def _anchor_names(path: Path) -> set[str]:
    """Collect heading and explicit HTML anchors from a document."""
    text = _without_code(path.read_text(encoding="utf-8"))
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
    cleaned = _without_code(text)

    for pattern in (_INLINE_LINK_RE, _REFERENCE_LINK_RE):
        for match in pattern.finditer(cleaned):
            target = match.group(1) or match.group(2)
            line = cleaned.count("\n", 0, match.start()) + 1
            yield html.unescape(target), line

    for match in _HTML_LINK_RE.finditer(cleaned):
        line = cleaned.count("\n", 0, match.start()) + 1
        yield html.unescape(match.group(2)), line


def _display_path(path: Path, root: Path) -> str:
    """Return a project-relative path when possible."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


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

    source_name = _display_path(source, root)
    if not destination.exists():
        return f"{source_name}:{line_number}: broken link '{target}'"

    fragment = unquote(parsed.fragment)
    if fragment and destination.suffix.lower() in {".md", ".html", ".htm"}:
        if destination not in anchor_cache:
            anchor_cache[destination] = _anchor_names(destination)

        if fragment not in anchor_cache[destination]:
            destination_name = _display_path(destination, root)
            return (
                f"{source_name}:{line_number}: missing anchor "
                f"'#{fragment}' in '{destination_name}'"
            )

    return None


def check_markdown_links(root: Path) -> list[str]:
    """Check local Markdown, HTML, and reference links and their anchors."""
    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}

    for source in _markdown_files(root):
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


def _h2_headings(path: Path) -> list[str]:
    """Return the ordered H2 headings in a Markdown document."""
    text = _without_code(path.read_text(encoding="utf-8"))
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

    for russian_path in _markdown_files(root):
        if not russian_path.name.endswith(".ru.md"):
            continue

        english_path = Path(str(russian_path)[: -len(".ru.md")] + ".md")
        if not english_path.is_file():
            errors.append(f"{_display_path(russian_path, root)}: missing English twin")
            continue

        english = _h2_headings(english_path)
        russian = _h2_headings(russian_path)

        if len(english) != len(russian):
            errors.append(
                f"{_display_path(russian_path, root)}: H2 section count "
                f"differs from {_display_path(english_path, root)} "
                f"({len(russian)} != {len(english)})"
            )
            continue

        english_numbers = [_section_number(heading) for heading in english]
        russian_numbers = [_section_number(heading) for heading in russian]

        if (any(english_numbers) or any(russian_numbers)) and (
            english_numbers != russian_numbers
        ):
            errors.append(
                f"{_display_path(russian_path, root)}: H2 section order "
                f"differs from {_display_path(english_path, root)}"
            )

    return errors


def check_russian_documents(root: Path) -> list[str]:
    """Ensure every Russian Markdown document contains Cyrillic characters."""
    return [
        f"{_display_path(path, root)}: no Cyrillic characters"
        for path in _markdown_files(root)
        if path.name.endswith(".ru.md")
        and re.search(
            r"[\u0400-\u04ff]",
            path.read_text(encoding="utf-8"),
        )
        is None
    ]


def _settings_environment_names() -> set[str]:
    """Return environment names corresponding to public Settings fields."""
    return {
        item.name
        for item in fields(Settings)
        if not item.name.startswith("_") and item.name not in _NON_ENVIRONMENT_FIELDS
    }


def check_settings(root: Path) -> list[str]:
    """Check settings correspondence with the environment example and guide."""
    errors: list[str] = []
    example_path = root / ".env.example"
    docs_path = root / "docs" / "configuration.md"

    if not example_path.is_file():
        errors.append(".env.example: file not found")
    if not docs_path.is_file():
        errors.append("docs/configuration.md: file not found")
    if errors:
        return errors

    settings_names = _settings_environment_names()
    example_names = set(
        _ENV_ASSIGNMENT_LINE_RE.findall(example_path.read_text(encoding="utf-8"))
    )
    docs_names = set(_CONFIG_SETTING_RE.findall(docs_path.read_text(encoding="utf-8")))

    missing_example = sorted(settings_names - example_names)
    extra_example = sorted(example_names - settings_names)

    if missing_example:
        errors.append(
            ".env.example: missing Settings fields: " + ", ".join(missing_example)
        )
    if extra_example:
        errors.append(".env.example: unknown settings: " + ", ".join(extra_example))

    expected_docs = settings_names | DOCUMENTATION_ONLY_ENV_NAMES
    missing_docs = sorted(expected_docs - docs_names)
    extra_docs = sorted(docs_names - expected_docs)

    if missing_docs:
        errors.append(
            "docs/configuration.md: missing settings: " + ", ".join(missing_docs)
        )
    if extra_docs:
        errors.append(
            "docs/configuration.md: unknown settings: " + ", ".join(extra_docs)
        )

    return errors


def _code_segments(text: str) -> list[str]:
    """Return fenced and inline code segments from Markdown."""
    blocks = list(_FENCED_BLOCK_RE.finditer(text))
    segments = [match.group(2) for match in blocks]
    remainder = _FENCED_BLOCK_RE.sub("", text)
    segments.extend(re.findall(r"`([^`\n]+)`", remainder))
    return segments


def _command_prefix_is_valid(tokens: list[str]) -> bool:
    """Check whether tokens before an executable are shell wrappers."""
    wrappers = {"sudo", "env", "doas", "time", "nohup", "command", "exec"}
    return all(
        token in wrappers or _ENV_ASSIGNMENT_RE.fullmatch(token) is not None
        for token in tokens
    )


_COMMAND_END_TOKENS = frozenset({"&&", "||", ";", "|", ">", ">>", "<"})


def _command_arguments(tokens: list[str], index: int) -> list[str]:
    """Return the arguments after the command at ``index`` up to a shell operator."""
    arguments: list[str] = []
    for item in tokens[index + 1 :]:
        if item in _COMMAND_END_TOKENS:
            break
        arguments.append(item)
    return arguments


def _commands_in_line(tokens: list[str]) -> Iterator[list[str]]:
    """Yield the argument list of every documented bot-obormot call in one line."""
    for index, token in enumerate(tokens):
        if _ENV_ASSIGNMENT_RE.fullmatch(token) is not None:
            continue
        if Path(token).name != "bot-obormot":
            continue
        if not _command_prefix_is_valid(tokens[:index]):
            continue

        arguments = _command_arguments(tokens, index)
        if arguments:
            yield arguments


def _documented_commands(segment: str) -> Iterator[list[str]]:
    """Extract bot-obormot CLI argument lists from shell and inline code."""
    logical_text = re.sub(r"\\\s*\n", " ", segment)

    for line in logical_text.splitlines():
        try:
            tokens = shlex.split(line, comments=True)
        except ValueError:
            continue

        yield from _commands_in_line(tokens)


def _cli_command_is_valid(arguments: list[str]) -> bool:
    """Return whether the CLI parser accepts a documented command."""
    try:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            build_parser().parse_args(arguments)
    except SystemExit as error:
        return error.code == 0
    return True


def check_documented_commands(root: Path) -> list[str]:
    """Check documented bot-obormot commands against the real CLI parser."""
    errors: list[str] = []

    for path in _markdown_files(root):
        text = path.read_text(encoding="utf-8")
        for segment in _code_segments(text):
            for arguments in _documented_commands(segment):
                if not _cli_command_is_valid(arguments):
                    command = " ".join(("bot-obormot", *arguments))
                    errors.append(
                        f"{_display_path(path, root)}: invalid CLI command '{command}'"
                    )

    return errors


def check_telegram_commands(root: Path) -> list[str]:
    """Check that every Telegram command in the sources is in the commands guide."""
    docs_path = root / "docs" / "commands.md"
    if not docs_path.is_file():
        return ["docs/commands.md: file not found"]

    declared: set[str] = set()
    for source in sorted((root / "bot_obormot").rglob("*.py")):
        declared.update(
            _COMMAND_DECLARATION_RE.findall(source.read_text(encoding="utf-8"))
        )

    documented = docs_path.read_text(encoding="utf-8")
    missing = sorted(name for name in declared if f"/{name}" not in documented)
    if missing:
        names = ", ".join(f"/{name}" for name in missing)
        return [f"docs/commands.md: missing commands: {names}"]
    return []


def check_docs(root: Path = PROJECT_ROOT) -> list[str]:
    """Run every documentation consistency check and return its errors."""
    errors: list[str] = []

    for check in (
        check_markdown_links,
        check_section_parity,
        check_russian_documents,
        check_settings,
        check_documented_commands,
        check_telegram_commands,
    ):
        errors.extend(check(root))

    return errors


def main() -> int:
    """Run documentation checks and print any failures."""
    errors = check_docs()
    if errors:
        for error in errors:
            sys.stderr.write(f"ERROR: {error}\n")
        return 1

    sys.stdout.write("Documentation checks passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
