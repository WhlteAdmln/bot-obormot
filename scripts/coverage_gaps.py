# VENDORED: keep identical in bot-obormot and audiodoc. Source of truth: audiodoc.
# Copyright (c) 2026 Nikolai Zelensky
"""Report the files with the lowest measured coverage."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from defusedxml import ElementTree

_ROOT = Path(__file__).resolve().parents[1]
_BRANCH_COUNTS = re.compile(r"\((\d+)/(\d+)\)\s*$")
_BRANCH_FLAG = "true"
_LIMIT_ERROR = "Limit must be positive"
_CLASS_FILENAME_ERROR = "Missing class filename"
_LINE_HITS_ERROR = "Missing line hit count"
_BRANCH_METADATA_ERROR = "Missing branch coverage metadata"
_BRANCH_FORMAT_ERROR = "Invalid branch coverage metadata"
_BRANCH_COUNTS_ERROR = "Invalid branch coverage counts"
_EMPTY_REPORT_ERROR = "No file coverage data found"


def _source_prefix(root: ElementTree.Element) -> str:
    source_names = {
        Path(source.text.strip()).name
        for source in root.findall("./sources/source")
        if source.text and source.text.strip()
    }
    return next(iter(source_names)) if len(source_names) == 1 else ""


def _relative_filename(filename: str, source_prefix: str) -> str:
    path = Path(filename)
    first_part = path.parts[0] if path.parts else ""
    if source_prefix and not path.is_absolute() and first_part != source_prefix:
        return (Path(source_prefix) / path).as_posix()
    return path.as_posix()


def _branch_counts(line: ElementTree.Element) -> tuple[int, int]:
    condition_coverage = line.get("condition-coverage")
    if line.get("branch") == _BRANCH_FLAG and condition_coverage is None:
        raise ValueError(_BRANCH_METADATA_ERROR)
    if condition_coverage is None:
        return 0, 0

    match = _BRANCH_COUNTS.search(condition_coverage)
    if match is None:
        raise ValueError(_BRANCH_FORMAT_ERROR)
    covered, total = (int(value) for value in match.groups())
    if covered > total:
        raise ValueError(_BRANCH_COUNTS_ERROR)
    return total, covered


def _line_statistics(line: ElementTree.Element) -> tuple[int, int, int, int]:
    hits = line.get("hits")
    if hits is None:
        raise ValueError(_LINE_HITS_ERROR)
    covered = int(int(hits) > 0)
    branches, covered_branches = _branch_counts(line)
    return 1, covered, branches, covered_branches


def _class_statistics(
    class_element: ElementTree.Element,
    source_prefix: str,
) -> tuple[str, list[int]] | None:
    filename = class_element.get("filename")
    if not filename:
        raise ValueError(_CLASS_FILENAME_ERROR)

    filename = _relative_filename(filename, source_prefix)
    lines = class_element.findall("./lines/line")
    if not lines:
        return None

    statistics = [0, 0, 0, 0]
    for line in lines:
        for index, count in enumerate(_line_statistics(line)):
            statistics[index] += count
    return filename, statistics


def _file_statistics(root: ElementTree.Element) -> dict[str, list[int]]:
    source_prefix = _source_prefix(root)
    file_statistics: dict[str, list[int]] = {}

    for class_element in root.findall(".//class"):
        class_data = _class_statistics(class_element, source_prefix)
        if class_data is None:
            continue

        filename, statistics = class_data
        totals = file_statistics.setdefault(filename, [0, 0, 0, 0])
        for index, count in enumerate(statistics):
            totals[index] += count

    if not file_statistics:
        raise ValueError(_EMPTY_REPORT_ERROR)
    return file_statistics


def _coverage_percentage(statistics: list[int]) -> float:
    statements, covered_statements, branches, covered_branches = statistics
    total = statements + branches
    return 100.0 * (covered_statements + covered_branches) / total


def find_coverage_gaps(
    xml_path: Path,
    limit: int = 15,
) -> list[tuple[float, str]]:
    """Return files ordered by their combined statement and branch coverage.

    Args:
        xml_path: Path to the coverage.py XML report.
        limit: Maximum number of files to return.

    Returns:
        Tuples of coverage percentage and repository-relative file path.

    Raises:
        OSError: If the report cannot be read.
        ElementTree.ParseError: If the report is not valid XML.
        ValueError: If the report contains forbidden XML constructs (defusedxml
            raises a ``ValueError`` subclass) or the limit or metadata is invalid.
    """
    if limit < 1:
        raise ValueError(_LIMIT_ERROR)

    root = ElementTree.parse(xml_path, forbid_dtd=True).getroot()
    file_statistics = _file_statistics(root)
    results = [
        (_coverage_percentage(statistics), filename)
        for filename, statistics in file_statistics.items()
    ]
    return sorted(results)[:limit]


def main() -> int:
    """Print the files with the lowest coverage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xml", type=Path, default=_ROOT / "coverage.xml")
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()

    try:
        results = find_coverage_gaps(args.xml, args.limit)
    except (OSError, ElementTree.ParseError, ValueError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    sys.stdout.write(f"Files with lowest coverage (up to {args.limit}):\n")
    for percentage, filename in results:
        sys.stdout.write(f"{percentage:7.3f}% {filename}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
