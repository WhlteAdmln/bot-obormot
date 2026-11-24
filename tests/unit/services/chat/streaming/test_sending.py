# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for streaming sending."""

import pytest

from bot_obormot.services.chat.streaming.sending import is_entity_parse_error
from tests.support.chat_streaming import PARSE_ERROR, bad_request, network_error


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (bad_request(PARSE_ERROR), True),
        (bad_request("Bad Request: chat not found"), False),
        (network_error(), False),
        (RuntimeError("can't parse entities"), False),
    ],
)
def test_only_confirmed_parse_errors_are_entity_errors(
    error: Exception,
    *,
    expected: bool,
) -> None:
    assert is_entity_parse_error(error) is expected
