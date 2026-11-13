# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Splitting of Telegram HTML messages that exceed the length limit."""

import html
import re

from bot.utils.text import utf16_length

_utf16_length = utf16_length


def split_formatted_message(
    text: str,
    max_length: int = 3900,
) -> list[str]:
    """Splits Telegram HTML into parts without breaking tags or entities.

    Разбивает Telegram HTML на части, не разрывая HTML-теги
    и символьные сущности.

    Открытые теги закрываются в конце части и повторно
    открываются в начале следующей.
    """
    if not text:
        return []

    if max_length < 1:
        msg = "max_length должен быть больше нуля."
        raise ValueError(msg)

    token_pattern = re.compile(
        r"<(/?)(b|i|blockquote)>"
        r"|&(?:#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]+);"
        r"|[^<&]+"
        r"|[<&]"
    )

    chunks = []
    current = []
    open_tags: list[str] = []
    visible_length = 0

    def close_tags() -> str:
        return "".join(f"</{tag}>" for tag in reversed(open_tags))

    def start_next_chunk() -> None:
        nonlocal current, visible_length

        current = [f"<{tag}>" for tag in open_tags]
        visible_length = 0

    def flush() -> None:
        nonlocal current

        if not current:
            return

        chunk = "".join(current) + close_tags()

        if chunk:
            chunks.append(chunk)

        start_next_chunk()

    for match in token_pattern.finditer(text):
        token = match.group(0)

        # HTML-тег.
        if token.startswith("<"):
            closing = match.group(1)
            tag = match.group(2)

            current.append(token)

            if closing:
                if tag in open_tags:
                    # Удаляем соответствующий открытый тег.
                    index = len(open_tags) - 1 - open_tags[::-1].index(tag)
                    open_tags.pop(index)
            else:
                open_tags.append(tag)

            continue

        # HTML-сущность, например &amp; или &#128512;.
        if token.startswith("&") and token.endswith(";"):
            decoded = html.unescape(token)
            token_length = _utf16_length(decoded)

            if visible_length + token_length > max_length:
                flush()

            current.append(token)
            visible_length += token_length
            continue

        # Обычный текст. Разбиваем по Unicode-символам,
        # не разрывая emoji и другие многобайтовые символы.
        for char in token:
            char_length = _utf16_length(char)

            if visible_length + char_length > max_length:
                flush()

            current.append(char)
            visible_length += char_length

    if current:
        chunk = "".join(current) + close_tags()

        if chunk:
            chunks.append(chunk)

    return chunks
