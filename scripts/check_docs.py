# Copyright (c) 2026 Nikolai Zelensky
"""Check documentation links and consistency with application sources."""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.check_changelog import check_changelog
from scripts.docs_checks.cli_commands import check_documented_commands
from scripts.docs_checks.links import check_markdown_links
from scripts.docs_checks.russian import check_russian_documents, check_section_parity
from scripts.docs_checks.settings import check_settings
from scripts.docs_checks.telegram_commands import check_telegram_commands

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def check_docs(root: Path = PROJECT_ROOT) -> list[str]:
    """Run every documentation consistency check and return its errors."""
    errors: list[str] = []

    for check in (
        check_changelog,
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
