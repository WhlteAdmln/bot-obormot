# Copyright (c) 2026 Nikolai Zelensky
"""Tests for the test rules check."""

from pathlib import Path

import pytest

from scripts import check_test_rules


@pytest.fixture(name="project")
def project_fixture(tmp_path: Path) -> Path:
    """Build a minimal repository with an empty test tree."""
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    return tmp_path


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "from unittest.mock import MagicMock\n",
            "1: imports unittest.mock.MagicMock; use a fake from tests/support",
        ),
        (
            "\nimport mock.patch\n",
            "2: imports mock.patch; use a fake from tests/support",
        ),
        (
            "def test_sends_report(mailer):\n    mailer.send.assert_called_once()\n",
            "2: uses assert_called_once; assert on the state of a fake",
        ),
        (
            "def test_reads_quota(mocker):\n    assert mocker, 'quota'\n",
            "1: uses the mocker fixture; use a fake from tests/support",
        ),
        (
            "def test_parses_header():\n    class Payload:\n        size = 7\n",
            "1: defines class Payload inside test_parses_header; move it",
        ),
        (
            "import time\n\ndef test_expires_token():\n    time.sleep(0.3)\n",
            "4: calls time.sleep; wait for a condition instead",
        ),
        (
            "from time import monotonic, sleep\n",
            "1: imports time.sleep; wait for a condition instead",
        ),
        (
            "import os, tempfile\n",
            "1: imports tempfile; use tmp_path",
        ),
        (
            "def make_dir(tempfile):\n    return tempfile.mkdtemp()\n",
            "2: uses tempfile.mkdtemp; use tmp_path",
        ),
        (
            "def test_counts_pages():\n    # three pages expected\n    pass\n",
            "2: comment in a test function; only a pragma with a reason",
        ),
        (
            "def test_casts_value():\n    int('4')  # type: ignore[arg-type]\n",
            "2: comment in a test function; only a pragma with a reason",
        ),
    ],
)
def test_reports_rule_violation(source: str, expected: str) -> None:
    problems = check_test_rules.file_problems(source)
    assert problems == [expected], "the violation must be reported once"


@pytest.mark.parametrize(
    "source",
    [
        "def test_hashes_key():\n    run()  # noqa: S603  # fixed argument list\n",
        "def test_checks_owner():\n    run()  # pylint: disable=W0212 - seam\n",
        "# Copyright (c) 2026 Example\n\ndef test_lists_jobs():\n    pass\n",
        "import time\n\ndef _wait():\n    time.sleep(0.05)\n",
        "def test_counts_rows():\n    assert 2 == 2\n    assert 5 > 1\n",
        "class TestQueue:\n    def test_pops(self):\n        assert 1, 'pop'\n",
    ],
)
def test_accepts_module_that_follows_the_rules(source: str) -> None:
    problems = check_test_rules.file_problems(source)
    expected_empty: list[str] = []
    assert problems == expected_empty, "a module that follows the rules must pass"


def test_reports_comment_in_test_method() -> None:
    source = "class TestCache:\n    def test_evicts(self):\n        # oldest first\n"
    problems = check_test_rules.file_problems(source + "        pass\n")
    assert problems == ["3: comment in a test function; only a pragma with a reason"], (
        "a test method must follow the comment rule"
    )


def test_reports_test_with_two_asserts_in_strict_mode() -> None:
    source = "def test_sorts_names():\n    assert 3, 'a'\n    assert 8, 'b'\n"
    problems = check_test_rules.file_problems(source, strict=True)
    assert problems == ["1: test_sorts_names has 2 asserts, not one"], (
        "a strict test must assert once"
    )


def test_reports_assert_without_message_in_strict_mode() -> None:
    source = "def test_trims_title():\n    assert 'x'.strip() == 'x'\n"
    problems = check_test_rules.file_problems(source, strict=True)
    assert problems == ["2: assert without a failure message"], (
        "a strict assert must carry a message"
    )


def test_reports_strict_violation_of_a_listed_file(project: Path) -> None:
    test_file = project / "tests" / "unit" / "test_billing.py"
    test_file.write_text("def test_rounds_total():\n    assert 9 > 4\n")
    (project / "tests" / "strict_test_files.txt").write_text(
        "tests/unit/test_billing.py\n"
    )
    problems = check_test_rules.find_problems(project)
    assert problems == [
        "tests/unit/test_billing.py:2: assert without a failure message"
    ], "a listed file must follow the strict rules"


def test_reports_listed_file_that_does_not_exist(project: Path) -> None:
    (project / "tests" / "strict_test_files.txt").write_text(
        "tests/unit/test_missing_audit.py\n"
    )
    problems = check_test_rules.find_problems(project)
    assert problems == [
        (
            "tests/unit/test_missing_audit.py: listed in "
            "tests/strict_test_files.txt but the file does not exist"
        )
    ], "a listed file must exist"


def test_checks_conftest_modules(project: Path) -> None:
    conftest = project / "tests" / "conftest.py"
    conftest.write_text("from unittest import mock\n")
    problems = check_test_rules.find_problems(project)
    assert problems == [
        "tests/conftest.py:1: imports unittest.mock; use a fake from tests/support"
    ], "conftest modules must follow the rules"
