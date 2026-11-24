# VENDORED: keep identical in bot-obormot and audiodoc. Source of truth: audiodoc.
# Copyright (c) 2026 Nikolai Zelensky
"""Check the general test rules that a linter does not cover.

Every ``test_*.py`` and ``conftest.py`` below ``tests/`` must not use mocks
(``unittest.mock``, ``mock``, the ``mocker`` fixture or ``assert_called*``), define a
class inside a function, import ``time.sleep`` or use ``tempfile`` instead of
``tmp_path``. A test function must not call ``time.sleep``; a helper may poll with a
deadline. A comment inside a test function must be a tool pragma (``# noqa``,
``# pylint:``, ``# type:`` or ``# pragma:``) followed by a reason after ``  # `` or
`` - ``, as in ``# noqa: S105  # fake credential``.

``tests/strict_test_files.txt`` lists the files that also follow the strict rules:
each test has exactly one assert, and every assert has a failure message. A listed
file must exist; the list only grows.
"""

from __future__ import annotations

import ast
import io
import sys
import tokenize
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = Path("tests")
STRICT_FILE = Path("tests/strict_test_files.txt")
MOCK_MODULES = frozenset({"mock", "unittest.mock"})
MOCK_FIXTURE = "mocker"
MOCK_ASSERT_PREFIXES = ("assert_called", "assert_awaited")
MOCK_ASSERT_NAMES = frozenset(
    {"assert_any_call", "assert_has_calls", "assert_not_called", "assert_not_awaited"}
)
TEMPFILE_MODULE = "tempfile"
TIME_MODULE = "time"
SLEEP_NAME = "sleep"
PRAGMA_PREFIXES = ("# noqa", "# pylint:", "# type:", "# pragma:")
REASON_SEPARATORS = ("  # ", " - ")

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _is_mock_module(name: str | None) -> bool:
    return name is not None and (
        name in MOCK_MODULES or any(name.startswith(f"{m}.") for m in MOCK_MODULES)
    )


def _is_mock_assert(name: str) -> bool:
    return name in MOCK_ASSERT_NAMES or name.startswith(MOCK_ASSERT_PREFIXES)


def _is_module_attribute(node: ast.Attribute, module: str, attribute: str) -> bool:
    return (
        isinstance(node.value, ast.Name)
        and node.value.id == module
        and node.attr == attribute
    )


def _import_problems(node: ast.AST) -> Iterator[str]:
    if isinstance(node, ast.Import):
        for alias in node.names:
            if _is_mock_module(alias.name):
                yield f"imports {alias.name}; use a fake from tests/support"
            if alias.name == TEMPFILE_MODULE:
                yield "imports tempfile; use tmp_path"
    elif isinstance(node, ast.ImportFrom) and node.level == 0:
        for alias in node.names:
            imported = f"{node.module}.{alias.name}"
            if _is_mock_module(node.module) or _is_mock_module(imported):
                yield f"imports {imported}; use a fake from tests/support"
        if node.module == TEMPFILE_MODULE:
            yield "imports tempfile; use tmp_path"
        if node.module == TIME_MODULE and any(
            alias.name == SLEEP_NAME for alias in node.names
        ):
            yield "imports time.sleep; wait for a condition instead"


def _attribute_problems(node: ast.Attribute) -> Iterator[str]:
    if _is_mock_assert(node.attr):
        yield f"uses {node.attr}; assert on the state of a fake"
    if _is_module_attribute(node, TEMPFILE_MODULE, node.attr):
        yield f"uses tempfile.{node.attr}; use tmp_path"


def _function_problems(node: FunctionNode) -> Iterator[str]:
    arguments = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
    if any(argument.arg == MOCK_FIXTURE for argument in arguments):
        yield "uses the mocker fixture; use a fake from tests/support"
    for child in ast.walk(node):
        if isinstance(child, ast.ClassDef):
            yield f"defines class {child.name} inside {node.name}; move it"


def _node_problems(node: ast.AST) -> Iterator[str]:
    yield from _import_problems(node)
    if isinstance(node, ast.Attribute):
        yield from _attribute_problems(node)
    if isinstance(node, FunctionNode):
        yield from _function_problems(node)


def _test_functions(tree: ast.Module) -> Iterator[FunctionNode]:
    for node in tree.body:
        if isinstance(node, FunctionNode) and node.name.startswith("test"):
            yield node
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            yield from (
                child
                for child in node.body
                if isinstance(child, FunctionNode) and child.name.startswith("test")
            )


def _first_line(node: FunctionNode) -> int:
    return min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])


def _is_allowed_comment(text: str) -> bool:
    if not text.startswith(PRAGMA_PREFIXES):
        return False
    reasons = (text.partition(separator)[2] for separator in REASON_SEPARATORS)
    return any(reason.strip() for reason in reasons)


def _sleep_problems(tests: list[FunctionNode]) -> Iterator[str]:
    for test in tests:
        for node in ast.walk(test):
            if isinstance(node, ast.Attribute) and _is_module_attribute(
                node, TIME_MODULE, SLEEP_NAME
            ):
                yield f"{node.lineno}: calls time.sleep; wait for a condition instead"


def _comment_problems(source: str, tests: list[FunctionNode]) -> Iterator[str]:
    spans = [(_first_line(test), test.end_lineno or test.lineno) for test in tests]
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        line = token.start[0]
        if any(start <= line <= end for start, end in spans) and not (
            _is_allowed_comment(token.string)
        ):
            yield f"{line}: comment in a test function; only a pragma with a reason"


def _strict_problems(tests: list[FunctionNode]) -> Iterator[str]:
    for test in tests:
        asserts = [node for node in ast.walk(test) if isinstance(node, ast.Assert)]
        if len(asserts) != 1:
            yield f"{test.lineno}: {test.name} has {len(asserts)} asserts, not one"
        for node in asserts:
            if node.msg is None:
                yield f"{node.lineno}: assert without a failure message"


def file_problems(source: str, *, strict: bool = False) -> list[str]:
    """Return the rule violations of one test module.

    Args:
        source: The source code of the test module.
        strict: Whether the module also follows the one-assert rules.

    Returns:
        Violations as ``<line>: <message>`` strings.
    """
    tree = ast.parse(source)
    problems = [
        f"{node.lineno}: {problem}"
        for node in ast.walk(tree)
        if isinstance(node, ast.stmt | ast.expr)
        for problem in _node_problems(node)
    ]
    tests = list(_test_functions(tree))
    problems.extend(_comment_problems(source, tests))
    problems.extend(_sleep_problems(tests))
    if strict:
        problems.extend(_strict_problems(tests))
    return sorted(set(problems), key=lambda problem: int(problem.split(":")[0]))


def read_strict(root: Path) -> list[str]:
    """Return the test files that follow the strict rules."""
    strict_file = root / STRICT_FILE
    if not strict_file.is_file():
        return []
    lines = strict_file.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def _test_files(root: Path) -> list[Path]:
    tests_dir = root / TESTS_DIR
    files = {*tests_dir.rglob("test_*.py"), *tests_dir.rglob("conftest.py")}
    return sorted(files)


def find_problems(root: Path) -> list[str]:
    """Return the test rule violations of a repository."""
    strict = set(read_strict(root))
    problems: list[str] = []
    seen: set[str] = set()
    for test_file in _test_files(root):
        name = test_file.relative_to(root).as_posix()
        seen.add(name)
        source = test_file.read_text(encoding="utf-8")
        problems.extend(
            f"{name}:{problem}"
            for problem in file_problems(source, strict=name in strict)
        )
    problems.extend(
        f"{name}: listed in {STRICT_FILE} but the file does not exist"
        for name in sorted(strict - seen)
    )
    return problems


def main() -> int:
    """Run the check and report violations."""
    problems = find_problems(PROJECT_ROOT)
    if problems:
        sys.stderr.write("Test rule violations:\n")
        sys.stderr.writelines(f"  {problem}\n" for problem in problems)
        return 1
    strict = len(read_strict(PROJECT_ROOT))
    sys.stdout.write(f"Test rule checks passed ({strict} files follow strict rules).\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
