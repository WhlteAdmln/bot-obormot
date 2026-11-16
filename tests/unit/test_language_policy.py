# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Enforce the source-code language policy."""

import ast
import io
import re
import tokenize
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BOT_ROOT = PROJECT_ROOT / "bot"
PROMPTS_ROOT = BOT_ROOT / "prompts"
ALLOWLIST_PATH = PROJECT_ROOT / "tests" / "language_allowlist.txt"
CYRILLIC_PATTERN = re.compile(r"[\u0400-\u04FF]")


def _has_language_violations(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")

    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT and CYRILLIC_PATTERN.search(token.string):
            return True

    tree = ast.parse(source, filename=str(path))

    for node in ast.walk(tree):
        if isinstance(
            node,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            docstring = ast.get_docstring(node, clean=False)
            if docstring is not None and CYRILLIC_PATTERN.search(docstring):
                return True

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if not CYRILLIC_PATTERN.search(node.value):
                continue
            if path.name != "texts.py" and not path.is_relative_to(PROMPTS_ROOT):
                return True

    return False


def test_python_language_policy_allowlist_is_exact() -> None:
    """Ensure the allowlist contains exactly the violating source files."""
    violations = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in sorted(BOT_ROOT.rglob("*.py"))
        if _has_language_violations(path)
    }
    allowlist = {
        line.strip()
        for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    missing_from_allowlist = sorted(violations - allowlist)
    already_clean = sorted(allowlist - violations)

    assert not missing_from_allowlist, (
        f"Language policy allowlist is missing violating files: "
        f"{missing_from_allowlist}"
    )
    assert not already_clean, (
        f"Language policy allowlist contains already clean files: {already_clean}"
    )
