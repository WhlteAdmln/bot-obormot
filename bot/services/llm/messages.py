"""Нормализация сообщений и подготовка мультимодального содержимого."""

import json
from typing import Any

from bot.errors import LLMUnavailableError


def normalize_content(content: Any) -> str | list:
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


def normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Проверяет структуру сообщений перед отправкой в API."""
    normalized = []

    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise LLMUnavailableError(f"Invalid message structure at index {index}")

        role = message.get("role")
        if not isinstance(role, str):
            raise LLMUnavailableError(f"Invalid message role at index {index}")

        content = normalize_content(message.get("content"))
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
