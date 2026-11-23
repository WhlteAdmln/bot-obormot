# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Shared helpers for audio documents tests."""

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Self
from urllib.parse import unquote

import aiohttp
from aiohttp.multipart import parse_content_disposition


class FakeContent:
    """Fake content."""

    def __init__(self, body: bytes) -> None:
        """Initializes the test double."""
        self._body = body

    async def iter_chunked(self, size: object) -> AsyncIterator[bytes]:
        """Iter chunked."""
        for start in range(0, len(self._body), size):
            yield self._body[start : start + size]


class FakeHTTPResponse:
    """Serve a fixed status and body as an aiohttp response context."""

    content_length = None

    def __init__(self, status: int = 200, body: bytes = b"") -> None:
        """Store the status and wrap the body in a chunked stream."""
        self.status = status
        self.content = FakeContent(body)

    async def __aenter__(self) -> Self:
        """Enter the response context."""
        return self

    async def __aexit__(self, *_args: object) -> bool:
        """Leave the response context without suppressing errors."""
        return False


class FakeHTTPSession:
    """Stand in for ``aiohttp.ClientSession`` and record its use."""

    def __init__(self, response: FakeHTTPResponse) -> None:
        """Store the response returned for every post."""
        self.response = response
        self.options: dict[str, object] = {}
        self.posts: list[dict[str, object]] = []

    def __call__(self, **options: object) -> Self:
        """Record the session options, as the ClientSession constructor would."""
        self.options = options
        return self

    async def __aenter__(self) -> Self:
        """Enter the session context."""
        return self

    async def __aexit__(self, *_args: object) -> bool:
        """Leave the session context without suppressing errors."""
        return False

    def post(self, url: str, data: object = None) -> FakeHTTPResponse:
        """Record the posted URL and form and return the stored response."""
        self.posts.append({"url": url, "data": data})
        return self.response


def form_fields(data: aiohttp.FormData) -> dict[str, tuple[str | None, str]]:
    """Map each multipart field name to its filename and decoded value."""
    fields = {}
    for payload, *_encodings in data():
        _kind, params = parse_content_disposition(
            payload.headers["Content-Disposition"]
        )
        filename = params.get("filename")
        fields[params["name"]] = (
            None if filename is None else unquote(filename),
            payload.decode(),
        )
    return fields


def json_body(payload: object) -> bytes:
    """Json body."""
    return json.dumps(payload).encode("utf-8")


def make_message(**values: object) -> SimpleNamespace:
    """Make message."""
    defaults = {"voice": None, "audio": None, "video_note": None}
    defaults.update(values)
    return SimpleNamespace(**defaults)
