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
            (
                "def test_sends_report(mailer):\n"
                "    mailer.send.assert_called_once()\n"
                "    assert mailer.outbox, 'outbox'\n"
            ),
            "2: uses assert_called_once; assert on the state of a fake",
        ),
        (
            "def test_reads_quota(mocker):\n    assert mocker, 'quota'\n",
            "1: uses the mocker fixture; use a fake from tests/support",
        ),
        (
            (
                "def test_parses_header():\n"
                "    class Payload:\n"
                "        size = 7\n"
                "    assert Payload.size == 7, 'size'\n"
            ),
            "1: defines class Payload inside test_parses_header; move it",
        ),
        (
            (
                "import time\n\ndef test_expires_token():\n"
                "    time.sleep(0.3)\n"
                "    assert time.time() > 0, 'clock'\n"
            ),
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
            (
                "def test_counts_pages():\n"
                "    # three pages expected\n"
                "    assert len('abc') == 3, 'pages'\n"
            ),
            "2: comment in a test function; only a pragma with a reason",
        ),
        (
            (
                "def test_casts_value():\n"
                "    value = int('4')  # type: ignore[arg-type]\n"
                "    assert value == 4, 'cast'\n"
            ),
            "2: comment in a test function; only a pragma with a reason",
        ),
        (
            (
                "def test_merges_chunks():\n"
                "    '''Merge two chunks.'''\n"
                "    assert 2 + 2 == 4, 'chunks'\n"
            ),
            "2: docstring in a test function; the test name describes it",
        ),
        (
            (
                "class TestLedger:\n"
                "    def test_books(self):\n"
                '        """Books."""\n'
                "        assert self, 'books'\n"
            ),
            "3: docstring in a test function; the test name describes it",
        ),
    ],
)
def test_reports_rule_violation(source: str, expected: str) -> None:
    problems = check_test_rules.file_problems(source)
    assert problems == [expected], "the violation must be reported once"


@pytest.mark.parametrize(
    "source",
    [
        "def test_hashes_key():\n    assert run(), 'key'  # noqa: S603  # fixed args\n",
        (
            "def test_checks_owner():\n"
            "    assert run(), 'own'  # pylint: disable=W0212 - seam\n"
        ),
        (
            "# Copyright (c) 2026 Example\n\n"
            "def test_lists_jobs():\n    assert jobs(), 'job'\n"
        ),
        "import time\n\ndef _wait():\n    time.sleep(0.05)\n",
        "def test_counts_rows():\n    assert len([4, 9]) == 2, 'rows'\n",
        "class TestQueue:\n    def test_pops(self):\n        assert 1, 'pop'\n",
        "def build_route():\n    '''Build a route for the map.'''\n",
    ],
)
def test_accepts_module_that_follows_the_rules(source: str) -> None:
    problems = check_test_rules.file_problems(source)
    expected_empty: list[str] = []
    assert problems == expected_empty, "a module that follows the rules must pass"


def test_reports_comment_in_test_method() -> None:
    source = "class TestCache:\n    def test_evicts(self):\n        # oldest first\n"
    problems = check_test_rules.file_problems(source + "        assert self, 'evict'\n")
    assert problems == ["3: comment in a test function; only a pragma with a reason"], (
        "a test method must follow the comment rule"
    )


def test_reports_test_with_two_asserts() -> None:
    source = "def test_sorts_names():\n    assert 3, 'a'\n    assert 8, 'b'\n"
    problems = check_test_rules.file_problems(source)
    assert problems == ["1: test_sorts_names has 2 asserts, not one"], (
        "a test must assert once"
    )


def test_reports_assert_without_message() -> None:
    source = "def test_trims_title():\n    assert 'x'.strip() == 'x'\n"
    problems = check_test_rules.file_problems(source)
    assert problems == ["2: assert without a failure message"], (
        "an assert must carry a message"
    )


def test_reports_assert_rule_violation_of_every_test_file(project: Path) -> None:
    test_file = project / "tests" / "unit" / "test_billing.py"
    test_file.write_text("def test_rounds_total():\n    assert 9 > 4\n")
    problems = check_test_rules.find_problems(project)
    assert problems == [
        "tests/unit/test_billing.py:2: assert without a failure message"
    ], "every test file must follow the assert rules"


def test_checks_conftest_modules(project: Path) -> None:
    conftest = project / "tests" / "conftest.py"
    conftest.write_text("from unittest import mock\n")
    problems = check_test_rules.find_problems(project)
    assert problems == [
        "tests/conftest.py:1: imports unittest.mock; use a fake from tests/support"
    ], "conftest modules must follow the rules"
