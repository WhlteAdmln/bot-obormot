# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the pure role checks."""

from collections.abc import Callable

import pytest

from bot_obormot.services.access.roles import (
    is_allowlisted,
    is_database_admin,
    is_supervisor,
)


@pytest.mark.parametrize(
    ("user_id", "supervisor_id", "expected"),
    [
        (731, 731, True),
        (731, 732, False),
        (-731, 731, False),
        (0, 731, False),
        (2**63 - 1, 2**63 - 1, True),
    ],
    ids=["same", "neighbour", "negated", "zero", "largest"],
)
def test_matches_only_the_supervisor_id(
    user_id: int, supervisor_id: int, *, expected: bool
) -> None:
    actual = is_supervisor(user_id, supervisor_id)
    assert actual is expected, "the supervisor check matched the wrong user"


@pytest.mark.parametrize("check", [is_database_admin, is_allowlisted])
@pytest.mark.parametrize(
    ("user_id", "listed_ids", "expected"),
    [
        (5150, {17, 5150}, True),
        (5150, {17, 5151}, False),
        (5150, set(), False),
        (-5150, {5150}, False),
        (0, {1}, False),
    ],
    ids=["listed", "not-listed", "empty", "negated", "zero"],
)
def test_matches_only_listed_ids(
    check: Callable[[int, set[int]], bool],
    user_id: int,
    listed_ids: set[int],
    *,
    expected: bool,
) -> None:
    actual = check(user_id, listed_ids)
    assert actual is expected, "the list check matched the wrong user"
