# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input models."""

from __future__ import annotations

import pytest

from tests.support.message_input import make_info


def test_message_info_without_any_kind_has_no_content() -> None:
    assert make_info().has_content is False, "an empty message has no content"


@pytest.mark.parametrize("kind", ["has_media", "has_audio", "has_document", "has_text"])
def test_message_info_has_content_for_each_supported_kind(kind: str) -> None:
    assert make_info(**{kind: True}).has_content is True, f"{kind} is content"
