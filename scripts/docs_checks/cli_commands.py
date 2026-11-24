# Copyright (c) 2026 Nikolai Zelensky
"""Check that documented CLI commands are accepted by the real parser."""

from __future__ import annotations

import re
import shlex
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

from bot_obormot.cli import build_parser
from scripts.docs_checks.markdown import code_segments, display_path, markdown_files

if TYPE_CHECKING:
    from collections.abc import Iterator

_COMMAND_NAME = "bot-obormot"
_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")


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
        if Path(token).name != _COMMAND_NAME:
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


def _parse_arguments_silently(arguments: list[str]) -> None:
    """Run the CLI parser without printing its usage or error messages."""
    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
        build_parser().parse_args(arguments)


def _cli_command_is_valid(arguments: list[str]) -> bool:
    """Return whether the CLI parser accepts a documented command."""
    try:
        _parse_arguments_silently(arguments)
    except SystemExit as error:
        return error.code == 0
    return True


def check_documented_commands(root: Path) -> list[str]:
    """Check documented bot-obormot commands against the real CLI parser."""
    errors: list[str] = []

    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8")
        for segment in code_segments(text):
            for arguments in _documented_commands(segment):
                if not _cli_command_is_valid(arguments):
                    command = " ".join((_COMMAND_NAME, *arguments))
                    errors.append(
                        f"{display_path(path, root)}: invalid CLI command '{command}'"
                    )

    return errors
