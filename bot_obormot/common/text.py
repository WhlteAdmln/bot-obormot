# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Small text helpers."""


def utf16_length(text: str) -> int:
    """Return the number of UTF-16 code units in text."""
    return len(text.encode("utf-16-le")) // 2


def log_safe(value: object, limit: int = 120) -> str:
    """Return a log-safe, truncated representation of value."""
    text = "" if value is None else str(value)
    text = text.replace("\r", "\\r").replace("\n", "\\n")
    text = "".join(ch if ch.isprintable() else "?" for ch in text)
    return text[:limit]
