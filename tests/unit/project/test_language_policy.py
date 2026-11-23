# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Enforce the source-code language policy."""

import ast
import io
import re
import tokenize
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BOT_ROOT = PROJECT_ROOT / "bot_obormot"
PROMPTS_ROOT = BOT_ROOT / "prompts"
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
            expected_name = "texts.py"
            if path.name != expected_name and not path.is_relative_to(PROMPTS_ROOT):
                return True

    return False


def test_python_language_policy_has_no_violations() -> None:
    """Ensure all Python source files follow the language policy."""
    violations = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in sorted(BOT_ROOT.rglob("*.py"))
        if _has_language_violations(path)
    }

    expected_empty = set()
    assert violations == expected_empty, (
        f"Python language policy violations found: {sorted(violations)}"
    )
