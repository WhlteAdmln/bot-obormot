# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Нормализация сообщений и подготовка мультимодального содержимого."""

import json
import re
from collections.abc import Sequence
from typing import Any

from bot.errors import LLMUnavailableError

_LITERALS = (
    "<s>",
    "</s>",
    "[INST]",
    "[/INST]",
    "<<SYS>>",
    "<</SYS>>",
    "<start_of_turn>",
    "<end_of_turn>",
)
_CONTROL_RE = re.compile(
    "|".join([r"<\|[^|>\n]{1,64}\|>"] + [re.escape(value) for value in _LITERALS]),
    re.IGNORECASE,
)


def neutralize_control_tokens(text: str) -> str:
    """Вставляет невидимый символ, чтобы служебная строка стала обычным текстом."""
    return _CONTROL_RE.sub(
        lambda match: match.group(0).replace("<", "<\u200b").replace("[", "[\u200b"),
        text,
    )


def _neutralize_content(content: object) -> object:
    """Neutralizes control tokens in string content and in text parts."""
    if isinstance(content, str):
        return neutralize_control_tokens(content)

    if isinstance(content, list):
        cleaned: list[Any] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                cleaned.append(
                    {
                        **part,
                        "text": neutralize_control_tokens(str(part.get("text", ""))),
                    }
                )
            elif isinstance(part, str):
                cleaned.append(neutralize_control_tokens(part))
            else:
                cleaned.append(part)
        return cleaned

    return content


def normalize_content(content: object) -> str | list[Any]:
    """Приводит content к допустимому формату API: строка или список частей."""
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        normalized = []
        for part in content:
            if isinstance(part, (str, dict)):
                normalized.append(part)
            else:
                normalized.append(str(part))
        return normalized

    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)

    return str(content)


def normalize_messages(messages: Sequence[object]) -> list[dict[str, Any]]:
    """Проверяет структуру сообщений перед отправкой в API."""
    normalized: list[dict[str, Any]] = []

    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            msg = f"Invalid message structure at index {index}"
            raise LLMUnavailableError(msg)

        role = message.get("role")
        if not isinstance(role, str):
            msg = f"Invalid message role at index {index}"
            raise LLMUnavailableError(msg)

        content: object = normalize_content(message.get("content"))

        if role != "system":
            content = _neutralize_content(content)

        normalized.append({**message, "role": role, "content": content})

    return normalized


def prepare_messages_for_count(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Убирает base64-данные изображений при подсчёте текстовых токенов."""
    prepared = []

    for message in messages:
        item = dict(message)
        content = item.get("content")

        if isinstance(content, list):
            prepared_content = []
            for part in content:
                if not isinstance(part, dict):
                    prepared_content.append(part)
                    continue

                prepared_part = dict(part)
                if prepared_part.get("type") == "image_url":
                    image_url = prepared_part.get("image_url")
                    if isinstance(image_url, dict):
                        prepared_part["image_url"] = {
                            **image_url,
                            "url": "data:image/jpeg;base64,",
                        }

                prepared_content.append(prepared_part)

            item["content"] = prepared_content

        prepared.append(item)

    return prepared


def count_images(messages: list[dict[str, Any]]) -> int:
    """Считает image_url-части во всех сообщениях."""
    count = 0

    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue

        count += sum(
            1
            for part in content
            if isinstance(part, dict) and part.get("type") == "image_url"
        )

    return count
