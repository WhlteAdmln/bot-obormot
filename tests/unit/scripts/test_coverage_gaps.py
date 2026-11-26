# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the coverage gap report script."""

from pathlib import Path

import pytest

from scripts.coverage_gaps import find_coverage_gaps, main


def _write_report(path: Path, classes: str) -> None:
    path.write_text(
        "<coverage><sources><source>/repo/audiodoc</source></sources>"
        "<packages><package><classes>"
        f"{classes}"
        "</classes></package></packages></coverage>",
        encoding="utf-8",
    )


def test_find_coverage_gaps_combines_statement_and_branch_coverage(
    tmp_path: Path,
) -> None:
    report = tmp_path / "coverage.xml"
    _write_report(
        report,
        """
        <class name="branchy.py" filename="branchy.py">
            <lines>
                <line number="1" hits="1"/>
                <line number="2" hits="0"/>
                <line number="3" hits="1" branch="true"
                      condition-coverage="50% (1/2)"/>
            </lines>
        </class>
        <class name="plain.py" filename="plain.py">
            <lines>
                <line number="1" hits="0"/>
                <line number="2" hits="1"/>
            </lines>
        </class>
        """,
    )

    expected = [
        (50.0, "audiodoc/plain.py"),
        (60.0, "audiodoc/branchy.py"),
    ]
    assert find_coverage_gaps(report) == expected, "the coverage gaps differ"


def test_find_coverage_gaps_returns_at_most_fifteen_files(tmp_path: Path) -> None:
    report = tmp_path / "coverage.xml"
    classes = "".join(
        f'<class name="file_{index:02d}.py" filename="file_{index:02d}.py">'
        '<lines><line number="1" hits="0"/></lines></class>'
        for index in range(16)
    )
    _write_report(report, classes)

    results = find_coverage_gaps(report)

    expected_count = 15
    assert len(results) == expected_count, "the report is not capped at 15 files"


def test_find_coverage_gaps_keeps_the_first_files_in_order(tmp_path: Path) -> None:
    report = tmp_path / "coverage.xml"
    classes = "".join(
        f'<class name="mod_{index:02d}.py" filename="mod_{index:02d}.py">'
        '<lines><line number="3" hits="0"/></lines></class>'
        for index in range(19)
    )
    _write_report(report, classes)

    results = find_coverage_gaps(report)

    expected = [f"audiodoc/mod_{index:02d}.py" for index in range(15)]
    assert [name for _, name in results] == expected, "the kept files differ"


def test_find_coverage_gaps_rejects_invalid_branch_coverage(tmp_path: Path) -> None:
    report = tmp_path / "coverage.xml"
    _write_report(
        report,
        """
        <class name="branchy.py" filename="branchy.py">
            <lines>
                <line number="1" hits="1" branch="true"
                      condition-coverage="invalid"/>
            </lines>
        </class>
        """,
    )

    with pytest.raises(ValueError, match="Invalid branch coverage metadata") as excinfo:
        find_coverage_gaps(report)

    assert excinfo.type is ValueError, "invalid branch coverage was not rejected"


def _write_dtd_report(path: Path, entity: str) -> None:
    path.write_text(
        f'<!DOCTYPE coverage [<!ENTITY payload "{entity}">]>'
        "<coverage><sources/><packages/></coverage>",
        encoding="utf-8",
    )


def _write_plain_report(path: Path) -> None:
    _write_report(
        path,
        """
        <class name="plain.py" filename="plain.py">
            <lines>
                <line number="1" hits="0"/>
                <line number="2" hits="1"/>
            </lines>
        </class>
        """,
    )


def test_main_rejects_dtd_declarations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = tmp_path / "coverage.xml"
    _write_dtd_report(report, "value")
    monkeypatch.setattr("sys.argv", ["coverage_gaps.py", "--xml", str(report)])

    expected_code = 1
    assert main() == expected_code, "a DTD declaration was accepted"


def test_main_reports_dtd_declarations_as_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = tmp_path / "dtd.xml"
    _write_dtd_report(report, "expanded entity")
    monkeypatch.setattr("sys.argv", ["coverage_gaps.py", "--xml", str(report)])

    main()

    prefix = "ERROR:"
    assert capsys.readouterr().err.startswith(prefix), "no error was printed"


def test_main_succeeds_for_a_valid_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = tmp_path / "valid.xml"
    _write_plain_report(report)
    monkeypatch.setattr(
        "sys.argv",
        ["coverage_gaps.py", "--xml", str(report), "--limit", "2"],
    )

    expected_code = 0
    assert main() == expected_code, "a valid report did not succeed"


def test_main_prints_requested_number_of_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = tmp_path / "coverage.xml"
    _write_plain_report(report)
    monkeypatch.setattr(
        "sys.argv",
        ["coverage_gaps.py", "--xml", str(report), "--limit", "1"],
    )

    main()

    expected_out = "Files with lowest coverage (up to 1):\n 50.000% audiodoc/plain.py\n"
    assert capsys.readouterr().out == expected_out, "the printed report differs"
