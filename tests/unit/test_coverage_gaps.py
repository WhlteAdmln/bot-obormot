# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for per-file branch coverage reporting."""

from pathlib import Path

import pytest

from scripts.coverage_gaps import find_lowest_branch_coverage


def test_find_lowest_branch_coverage_sorts_and_aggregates(
    tmp_path: Path,
) -> None:
    """Sort branch coverage and aggregate duplicate source files."""
    coverage_xml = tmp_path / "coverage.xml"
    coverage_xml.write_text(
        """<?xml version="1.0" ?>
<coverage>
  <packages>
    <package>
      <classes>
        <class filename="bot/a.py">
          <lines>
            <line number="1" branch="true" condition-coverage="50% (1/2)"/>
          </lines>
        </class>
        <class filename="bot/a.py">
          <lines>
            <line number="2" branch="true" condition-coverage="50% (1/2)"/>
          </lines>
        </class>
        <class filename="bot/b.py">
          <lines>
            <line number="1" branch="true" condition-coverage="0% (0/4)"/>
          </lines>
        </class>
        <class filename="bot/c.py">
          <lines>
            <line number="1" branch="true" condition-coverage="50% (1/2)"/>
          </lines>
        </class>
        <class filename="bot/no_branches.py">
          <lines>
            <line number="1" hits="1"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
""",
        encoding="utf-8",
    )

    assert find_lowest_branch_coverage(coverage_xml) == [
        ("bot/b.py", 0, 4),
        ("bot/a.py", 2, 4),
        ("bot/c.py", 1, 2),
    ]


def test_find_lowest_branch_coverage_limits_output_to_fifteen(
    tmp_path: Path,
) -> None:
    """Return no more than 15 files."""
    coverage_xml = tmp_path / "coverage.xml"
    classes = "".join(
        f'<class filename="bot/file_{index:02}.py"><lines>'
        f'<line branch="true" condition-coverage="{index}% ({index}/100)"/>'
        "</lines></class>"
        for index in range(16)
    )
    coverage_xml.write_text(
        f"<coverage><packages><package><classes>{classes}</classes>"
        "</package></packages></coverage>",
        encoding="utf-8",
    )

    rows = find_lowest_branch_coverage(coverage_xml)

    assert len(rows) == 15
    assert rows[0] == ("bot/file_00.py", 0, 100)
    assert rows[-1] == ("bot/file_14.py", 14, 100)


def test_find_lowest_branch_coverage_rejects_doctype(
    tmp_path: Path,
) -> None:
    """Reject XML documents containing a DOCTYPE declaration."""
    coverage_xml = tmp_path / "coverage.xml"
    coverage_xml.write_text(
        '<!DOCTYPE coverage [<!ENTITY name "bot/a.py">]>'
        '<coverage><class filename="&name;"><lines/></class></coverage>',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="DOCTYPE declarations are not supported"):
        find_lowest_branch_coverage(coverage_xml)
