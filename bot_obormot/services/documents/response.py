# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Validation of the Document Engine response structure."""

from typing import NotRequired, TypedDict, cast

from bot_obormot.errors import DocumentAPIError

_TRUNCATED_FIELD = "truncated"


class DocumentResponse(TypedDict):
    """Text extracted by the Document Engine and its metadata."""

    text: str
    format: str
    characters: int
    truncated: NotRequired[bool]


def validate_document_response(result: object) -> DocumentResponse:
    """Validate the Document Engine response structure without transforming data."""
    if not isinstance(result, dict):
        raise DocumentAPIError(
            502,
            "Invalid response from Document Engine",
        )

    if not isinstance(result.get("text"), str):
        raise DocumentAPIError(
            502,
            "Document Engine returned invalid text",
        )

    if not isinstance(result.get("format"), str):
        raise DocumentAPIError(
            502,
            "Document Engine returned invalid format",
        )

    characters = result.get("characters")
    # bool is a subclass of int, so a JSON true would pass a bare int check.
    if (
        not isinstance(characters, int)
        or isinstance(characters, bool)
        or characters < 0
    ):
        raise DocumentAPIError(
            502,
            "Document Engine returned invalid character count",
        )

    # Older audiodoc versions may omit this field; when present, it must be boolean.
    if _TRUNCATED_FIELD in result and not isinstance(result[_TRUNCATED_FIELD], bool):
        raise DocumentAPIError(
            502,
            "Document Engine returned invalid truncated flag",
        )

    return cast("DocumentResponse", result)
