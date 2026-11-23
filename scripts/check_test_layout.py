# VENDORED: keep identical in bot-obormot and audiodoc. Source of truth: audiodoc.
# Copyright (c) 2026 Nikolai Zelensky
"""Check that every unit test file mirrors a production unit.

A unit test file lives at ``tests/unit/<dirs>/test_<name>.py`` and tests either the
module ``<package>/<dirs>/<name>.py``, the package ``<package>/<dirs>/<name>/`` or the
class whose snake_case name is ``<name>`` in a module of ``<package>/<dirs>/``.
Tests that do not target one module (packaging, documentation, release workflow,
installer, scripts) live under ``tests/unit/project/`` or ``tests/unit/scripts/``.

``tests/layout_pending.txt`` lists files that still need to be moved. A listed file
must exist and must still break the layout; the list only shrinks.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UNIT_DIR = Path("tests/unit")
PENDING_FILE = Path("tests/layout_pending.txt")
EXEMPT_DIRS = ("project", "scripts")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def snake_case(name: str) -> str:
    """Convert a CamelCase class name to snake_case."""
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def package_name(root: Path) -> str:
    """Return the import package named after the project."""
    with (root / "pyproject.toml").open("rb") as handle:
        project_name = tomllib.load(handle)["project"]["name"]
    return str(project_name).replace("-", "_")


def _class_names(source_dir: Path) -> set[str]:
    """Return snake_case names of the top-level classes of a source directory."""
    names: set[str] = set()
    for module in sorted(source_dir.glob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        names.update(
            snake_case(node.name)
            for node in tree.body
            if isinstance(node, ast.ClassDef)
        )
    return names


def mirrors_unit(root: Path, package: str, test_file: Path) -> bool:
    """Return whether a unit test file mirrors a production unit."""
    relative = test_file.relative_to(root / UNIT_DIR)
    if relative.parts[0] in EXEMPT_DIRS and len(relative.parts) > 1:
        return True
    unit = test_file.stem.removeprefix("test_")
    source_dir = root / package / relative.parent
    return (
        (source_dir / f"{unit}.py").is_file()
        or (source_dir / unit / "__init__.py").is_file()
        or unit in _class_names(source_dir)
    )


def read_pending(root: Path) -> list[str]:
    """Return the files that are allowed to break the layout for now."""
    pending_file = root / PENDING_FILE
    if not pending_file.is_file():
        return []
    lines = pending_file.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def find_problems(root: Path) -> list[str]:
    """Return the layout violations of a repository."""
    package = package_name(root)
    pending = set(read_pending(root))
    problems: list[str] = []
    seen: set[str] = set()
    for test_file in sorted((root / UNIT_DIR).rglob("test_*.py")):
        name = test_file.relative_to(root).as_posix()
        seen.add(name)
        valid = mirrors_unit(root, package, test_file)
        if valid and name in pending:
            problems.append(f"{name}: already mirrors a unit; remove it from the list")
        elif not valid and name not in pending:
            problems.append(f"{name}: no production unit at the mirrored path")
    problems.extend(
        f"{name}: listed in {PENDING_FILE} but the file does not exist"
        for name in sorted(pending - seen)
    )
    return problems


def main() -> int:
    """Run the check and report violations."""
    problems = find_problems(PROJECT_ROOT)
    if problems:
        sys.stderr.write("Test layout violations:\n")
        sys.stderr.writelines(f"  {problem}\n" for problem in problems)
        return 1
    pending = len(read_pending(PROJECT_ROOT))
    sys.stdout.write(f"Test layout checks passed ({pending} files still pending).\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
