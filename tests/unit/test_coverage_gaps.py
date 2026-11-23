# Copyright (c) 2026 Nikolai Zelensky
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
):
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

    assert find_coverage_gaps(report) == [
        (50.0, "audiodoc/plain.py"),
        (60.0, "audiodoc/branchy.py"),
    ]


def test_find_coverage_gaps_returns_at_most_fifteen_files(tmp_path: Path):
    report = tmp_path / "coverage.xml"
    classes = "".join(
        f'<class name="file_{index:02d}.py" filename="file_{index:02d}.py">'
        '<lines><line number="1" hits="0"/></lines></class>'
        for index in range(16)
    )
    _write_report(report, classes)

    results = find_coverage_gaps(report)

    assert len(results) == 15
    assert [filename for _, filename in results] == [
        f"audiodoc/file_{index:02d}.py" for index in range(15)
    ]


def test_find_coverage_gaps_rejects_invalid_branch_coverage(tmp_path: Path):
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

    with pytest.raises(ValueError, match="Invalid branch coverage metadata"):
        find_coverage_gaps(report)


def test_main_rejects_dtd_declarations(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    report = tmp_path / "coverage.xml"
    report.write_text(
        '<!DOCTYPE coverage [<!ENTITY payload "value">]>'
        "<coverage><sources/><packages/></coverage>",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["coverage_gaps.py", "--xml", str(report)],
    )

    assert main() == 1
    assert capsys.readouterr().err.startswith("ERROR:")


def test_main_prints_requested_number_of_files(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    report = tmp_path / "coverage.xml"
    _write_report(
        report,
        """
        <class name="plain.py" filename="plain.py">
            <lines>
                <line number="1" hits="0"/>
                <line number="2" hits="1"/>
            </lines>
        </class>
        """,
    )
    monkeypatch.setattr(
        "sys.argv",
        ["coverage_gaps.py", "--xml", str(report), "--limit", "1"],
    )

    assert main() == 0
    assert capsys.readouterr().out == (
        "Files with lowest coverage (up to 1):\n 50.000% audiodoc/plain.py\n"
    )
