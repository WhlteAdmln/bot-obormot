# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Conversion of roleplay markup into Telegram HTML."""

import html


def _render_segment(text: str) -> str:
    """Преобразует ролевую разметку в безопасный Telegram HTML.

    *текст*   -> курсив
    **текст** -> жирный
    ~текст~   -> блок мыслей

    Незакрытые маркеры остаются обычным текстом.
    """
    markers = {
        "**": "b",
        "*": "i",
        "~": "blockquote",
    }

    result = []
    i = 0

    while i < len(text):
        marker = None

        # Двойная звёздочка проверяется раньше одинарной.
        for candidate in ("**", "*", "~"):
            if text.startswith(candidate, i):
                marker = candidate
                break

        if marker is None:
            # Собираем обычный текст до следующего маркера.
            next_positions = [
                pos for symbol in markers if (pos := text.find(symbol, i)) != -1
            ]

            next_pos = min(next_positions) if next_positions else len(text)

            result.append(html.escape(text[i:next_pos], quote=False))
            i = next_pos
            continue

        closing = text.find(marker, i + len(marker))

        if closing == -1 or closing == i + len(marker):
            # Незакрытый или пустой маркер показываем буквально.
            result.append(html.escape(marker, quote=False))
            i += len(marker)
            continue

        tag = markers[marker]
        inner = text[i + len(marker) : closing]

        formatted_inner = _render_segment(inner)

        if tag == "blockquote":
            result.append(f"\n<blockquote><i>{formatted_inner}</i></blockquote>\n")
        else:
            result.append(f"<{tag}>{formatted_inner}</{tag}>")

        i = closing + len(marker)

    return "".join(result)


def format_roleplay(text: str) -> str:
    """Преобразует ответ персонажа в Telegram HTML."""
    if not text:
        return ""

    return _render_segment(text.strip())
