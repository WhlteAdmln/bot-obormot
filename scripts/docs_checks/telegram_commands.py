# Copyright (c) 2026 Nikolai Zelensky
"""Check that every Telegram command in the sources is in the commands guide."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_COMMAND_DECLARATION_RE = re.compile(r"Command\(\"([a-z_]+)\"")


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
