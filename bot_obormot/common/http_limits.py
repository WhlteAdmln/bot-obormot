# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Read HTTP response bodies with a size limit."""

import aiohttp

MAX_SERVICE_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_ERROR_BODY_BYTES = 2048


async def read_limited_body(
    response: aiohttp.ClientResponse,
    limit: int,
) -> bytes | None:
    """Return the response body, or None if it exceeds the byte limit."""
    if response.content_length is not None and response.content_length > limit:
        return None

    chunks: list[bytes] = []
    total = 0

    async for chunk in response.content.iter_chunked(64 * 1024):
        total += len(chunk)

        if total > limit:
            return None

        chunks.append(chunk)

    return b"".join(chunks)


async def read_body_prefix(
    response: aiohttp.ClientResponse,
    limit: int,
) -> tuple[bytes, bool]:
    """Return at most ``limit`` bytes of the body and whether more bytes followed."""
    chunks: list[bytes] = []
    total = 0

    async for chunk in response.content.iter_chunked(64 * 1024):
        room = limit - total
        if len(chunk) > room:
            chunks.append(chunk[:room])
            return b"".join(chunks), True

        chunks.append(chunk)
        total += len(chunk)

    return b"".join(chunks), False
