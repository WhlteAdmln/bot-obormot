# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Report files with the lowest branch coverage."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from xml.parsers import expat

_BRANCH_COUNTS = re.compile(r"\((\d+)/(\d+)\)")


class _UnsupportedDoctypeError(ValueError):
    """Raised when a coverage report declares a document type."""

    def __init__(self) -> None:
        message = "DOCTYPE declarations are not supported."
        super().__init__(message)


def find_lowest_branch_coverage(
    coverage_xml: Path,
) -> list[tuple[str, int, int]]:
    """Return files ordered by ascending branch coverage."""
    totals_by_file: dict[str, list[int]] = {}
    current_filename: str | None = None

    def reject_doctype(
        name: str,
        system_id: str | None,
        public_id: str | None,
        has_internal_subset: int,
    ) -> None:
        del name, system_id, public_id, has_internal_subset
        raise _UnsupportedDoctypeError

    def start_element(name: str, attributes: dict[str, str]) -> None:
        nonlocal current_filename

        if name == "class":
            current_filename = attributes.get("filename")
            if current_filename is not None:
                totals_by_file.setdefault(current_filename, [0, 0])
        elif name == "line" and current_filename is not None:
            if attributes.get("branch") != "true":
                return

            match = _BRANCH_COUNTS.search(attributes.get("condition-coverage", ""))
            if match is None:
                return

            covered, total = (int(value) for value in match.groups())
            totals = totals_by_file[current_filename]
            totals[0] += covered
            totals[1] += total

    def end_element(name: str) -> None:
        nonlocal current_filename
        if name == "class":
            current_filename = None

    parser = expat.ParserCreate()
    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    parser.StartDoctypeDeclHandler = reject_doctype
    is_final: bool = True
    parser.Parse(coverage_xml.read_bytes(), is_final)

    rows = [
        (filename, covered, total)
        for filename, (covered, total) in totals_by_file.items()
        if total > 0
    ]
    return sorted(rows, key=lambda row: (row[1] / row[2], row[0]))[:15]


def main() -> int:
    """Print the 15 files with the lowest branch coverage."""
    coverage_xml = Path(__file__).resolve().parents[1] / "coverage.xml"

    try:
        rows = find_lowest_branch_coverage(coverage_xml)
    except (OSError, expat.ExpatError, ValueError) as exc:
        sys.stderr.write(f"Cannot read coverage report {coverage_xml}: {exc}\n")
        return 1

    if not rows:
        sys.stdout.write("No branch coverage data found.\n")
        return 0

    sys.stdout.write("Files with the lowest branch coverage:\n")
    for filename, covered, total in rows:
        sys.stdout.write(f"{covered / total:.1%} ({covered}/{total}) {filename}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
