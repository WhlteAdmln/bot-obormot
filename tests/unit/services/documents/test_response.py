# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for documents response."""

import pytest

from bot_obormot.errors import DocumentAPIError
from bot_obormot.services.documents.response import validate_document_response


def _failure(payload: object) -> tuple[int, str]:
    try:
        validate_document_response(payload)
    except DocumentAPIError as error:
        return error.status, error.detail
    return 0, ""


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "Текст", "format": "pdf", "characters": 5, "truncated": False},
        {"text": "", "format": "docx", "characters": 0},
        {"text": "x", "format": "txt", "characters": 1, "truncated": True, "pages": 3},
    ],
    ids=["full", "without-truncated-flag", "extra-field"],
)
def test_returns_a_valid_payload_without_copying(payload: dict[str, object]) -> None:
    assert validate_document_response(payload) is payload, "the payload was copied"


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ([], "Invalid response from Document Engine"),
        ("<html>502 Bad Gateway</html>", "Invalid response from Document Engine"),
        (None, "Invalid response from Document Engine"),
        ({"format": "pdf", "characters": 1}, "Document Engine returned invalid text"),
        (
            {"text": ["x"], "format": "pdf", "characters": 1},
            "Document Engine returned invalid text",
        ),
        ({"text": "x", "characters": 1}, "Document Engine returned invalid format"),
        (
            {"text": "x", "format": 7, "characters": 1},
            "Document Engine returned invalid format",
        ),
        (
            {"text": "x", "format": "pdf"},
            "Document Engine returned invalid character count",
        ),
        (
            {"text": "x", "format": "pdf", "characters": "1"},
            "Document Engine returned invalid character count",
        ),
        (
            {"text": "x", "format": "pdf", "characters": True},
            "Document Engine returned invalid character count",
        ),
        (
            {"text": "x", "format": "pdf", "characters": -7},
            "Document Engine returned invalid character count",
        ),
        (
            {"text": "x", "format": "pdf", "characters": 1, "truncated": "false"},
            "Document Engine returned invalid truncated flag",
        ),
        (
            {"text": "x", "format": "pdf", "characters": 1, "truncated": None},
            "Document Engine returned invalid truncated flag",
        ),
        (
            {"text": "x", "format": "pdf", "characters": 1, "truncated": 0},
            "Document Engine returned invalid truncated flag",
        ),
    ],
    ids=[
        "list",
        "html",
        "null",
        "missing-text",
        "list-text",
        "missing-format",
        "numeric-format",
        "missing-count",
        "string-count",
        "boolean-count",
        "negative-count",
        "string-flag",
        "null-flag",
        "integer-flag",
    ],
)
def test_rejects_a_malformed_payload_as_bad_gateway(
    payload: object, detail: str
) -> None:
    expected = (502, detail)
    assert _failure(payload) == expected, "a malformed payload must be rejected"
