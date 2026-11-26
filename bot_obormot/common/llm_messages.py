# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Chat messages and content parts of the OpenAI-compatible API."""

from typing import Literal, TypedDict


class ImageURL(TypedDict):
    """The address of an image, usually a base64 data URL."""

    url: str


class TextPart(TypedDict):
    """A text part of multimodal message content."""

    type: Literal["text"]
    text: str


class ImageURLPart(TypedDict):
    """An image part of multimodal message content."""

    type: Literal["image_url"]
    image_url: ImageURL


ContentPart = TextPart | ImageURLPart
MessageContent = str | list[ContentPart]


class ChatMessage(TypedDict):
    """A chat message with a role and text or multimodal content."""

    role: str
    content: MessageContent


__all__ = [
    "ChatMessage",
    "ContentPart",
    "ImageURL",
    "ImageURLPart",
    "MessageContent",
    "TextPart",
]
