# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""HTTP plumbing shared by the audiodoc transcription and document clients."""

import json
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from bot_obormot.common.http_limits import (
    MAX_ERROR_BODY_BYTES,
    MAX_SERVICE_RESPONSE_BYTES,
    read_body_prefix,
    read_limited_body,
)
from bot_obormot.settings import Settings, get_settings

MAX_ERROR_DETAIL_CHARS = 1000
TRUNCATED_MARKER = " [truncated]"


@dataclass(frozen=True, slots=True)
class FormResponse:
    """Status and size-limited body of one audiodoc response."""

    status: int
    body: bytes | None
    truncated: bool = False

    @property
    def detail(self) -> str:
        """Return the body as text for an error message, marked when cut short."""
        text = (self.body or b"").decode("utf-8", errors="replace")
        if self.truncated or len(text) > MAX_ERROR_DETAIL_CHARS:
            return text[:MAX_ERROR_DETAIL_CHARS] + TRUNCATED_MARKER
        return text

    def json(self) -> object:
        """Decode the body as JSON; raise ``ValueError`` when it is not JSON."""
        return json.loads(self.body or b"")


def endpoint_url(base_url: str, endpoint: str) -> str:
    """Append an endpoint to the base URL path, keeping its query string."""
    parts = urlsplit(base_url)
    path = f"{parts.path.rstrip('/')}/{endpoint}"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def require_base_url(
    settings: Settings | None,
    error: type[Exception],
) -> Settings:
    """Return the effective settings or raise ``error`` without AUDIODOC_URL."""
    effective = get_settings() if settings is None else settings
    if not effective.AUDIODOC_URL:
        msg = "AUDIODOC_URL is not configured"
        raise error(msg)
    return effective


def file_form(data: bytes, filename: str) -> aiohttp.FormData:
    """Build a multipart form whose ``file`` field carries the data."""
    form = aiohttp.FormData()
    form.add_field(
        "file",
        data,
        filename=filename,
        content_type="application/octet-stream",
    )
    return form


def bearer_headers(api_key: str) -> dict[str, str]:
    """Return the authorization header for a non-empty API key."""
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def post_form(
    url: str,
    form: aiohttp.FormData,
    client_timeout: aiohttp.ClientTimeout,
    headers: dict[str, str],
) -> FormResponse:
    """Post the form and read a size-limited body.

    An error body keeps its first bytes up to the smaller error limit and is
    marked as truncated when it is longer; a success body that exceeds the
    response limit is returned as ``None``.
    """
    async with (
        aiohttp.ClientSession(
            timeout=client_timeout,
            headers=headers,
        ) as session,
        session.post(url, data=form) as response,
    ):
        if response.status == HTTPStatus.OK:
            body = await read_limited_body(response, MAX_SERVICE_RESPONSE_BYTES)
            return FormResponse(response.status, body)

        prefix, truncated = await read_body_prefix(response, MAX_ERROR_BODY_BYTES)
        return FormResponse(response.status, prefix, truncated)
