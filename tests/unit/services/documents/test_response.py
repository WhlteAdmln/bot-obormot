# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for documents response."""

import pytest

from bot_obormot.errors import (
    DocumentAPIError,
)
from bot_obormot.services.documents.response import validate_document_response


def test_validate_document_response_accepts_valid_payload_without_copying() -> None:
    """Validate document response accepts valid payload without copying."""
    payload = {
        "text": "Текст",
        "format": "pdf",
        "characters": 5,
        "truncated": False,
    }
    assert validate_document_response(payload) is payload


def test_validate_document_response_rejects_non_boolean_truncated_flag() -> None:
    """Validate document response rejects non boolean truncated flag."""
    payload = {
        "text": "Текст",
        "format": "pdf",
        "characters": 5,
        "truncated": "false",
    }
    with pytest.raises(DocumentAPIError, match="invalid truncated flag"):
        validate_document_response(payload)


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ([], "Invalid response from Document Engine"),
        ({"format": "pdf", "characters": 1}, "invalid text"),
        ({"text": "x", "characters": 1}, "invalid format"),
        ({"text": "x", "format": "pdf"}, "invalid character count"),
    ],
)
def test_validate_document_response_rejects_invalid_payloads(
    payload: object, detail: str
) -> None:
    """Validate document response rejects invalid payloads."""
    with pytest.raises(DocumentAPIError, match=detail):
        validate_document_response(payload)
