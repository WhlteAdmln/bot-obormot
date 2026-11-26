# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Normalize messages and prepare multimodal content."""

import json
import re
from collections.abc import Mapping, Sequence
from typing import cast

from bot_obormot.common.llm_messages import ChatMessage
from bot_obormot.errors import LLMUnavailableError
from bot_obormot.services.llm.constants import (
    PART_TYPE_IMAGE_URL,
    PART_TYPE_TEXT,
    ROLE_SYSTEM,
)

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
    """Insert an invisible character to turn control strings into plain text."""
    return _CONTROL_RE.sub(
        lambda match: match.group(0).replace("<", "<\u200b").replace("[", "[\u200b"),
        text,
    )


def _neutralize_content(content: object) -> object:
    """Neutralizes control tokens in string content and in text parts."""
    if isinstance(content, str):
        return neutralize_control_tokens(content)

    if isinstance(content, list):
        cleaned: list[object] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == PART_TYPE_TEXT:
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


def normalize_content(content: object) -> str | list[object]:
    """Convert content to a valid API format: a string or a list of parts."""
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        normalized: list[object] = []
        for part in content:
            if isinstance(part, (str, dict)):
                normalized.append(part)
            else:
                normalized.append(str(part))
        return normalized

    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)

    return str(content)


def normalize_messages(messages: Sequence[object]) -> list[ChatMessage]:
    """Validate message structures before sending them to the API."""
    normalized: list[ChatMessage] = []

    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            msg = f"Invalid message structure at index {index}"
            raise LLMUnavailableError(msg)

        role = message.get("role")
        if not isinstance(role, str):
            msg = f"Invalid message role at index {index}"
            raise LLMUnavailableError(msg)

        content: object = normalize_content(message.get("content"))

        if role != ROLE_SYSTEM:
            content = _neutralize_content(content)

        # Content parts are passed through as given; only the role is checked.
        normalized.append(
            cast("ChatMessage", {**message, "role": role, "content": content})
        )

    return normalized


def prepare_messages_for_count(
    messages: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Remove image base64 data when counting text tokens."""
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
                if prepared_part.get("type") == PART_TYPE_IMAGE_URL:
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


def count_images(messages: Sequence[Mapping[str, object]]) -> int:
    """Count image_url parts across all messages."""
    count = 0

    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue

        count += sum(
            1
            for part in content
            if isinstance(part, dict) and part.get("type") == PART_TYPE_IMAGE_URL
        )

    return count
