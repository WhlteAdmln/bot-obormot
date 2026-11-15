# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Small text helpers."""


def utf16_length(text: str) -> int:
    """Возвращает длину текста в кодовых единицах UTF-16."""
    return len(text.encode("utf-16-le")) // 2


def log_safe(value: object, limit: int = 120) -> str:
    """Делает значение безопасным для лога: без переводов строк, коротко."""
    text = "" if value is None else str(value)
    text = text.replace("\r", "\\r").replace("\n", "\\n")
    text = "".join(ch if ch.isprintable() else "?" for ch in text)
    return text[:limit]
