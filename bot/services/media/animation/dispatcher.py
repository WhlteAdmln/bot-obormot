# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Dispatch of animation decoding by media format."""

from collections.abc import Callable

from bot.services.media.animation.gif import extract_gif
from bot.services.media.animation.tgs import extract_tgs
from bot.services.media.animation.video import extract_video

FrameExtractor = Callable[[bytes], list[bytes]]


def dispatch_extraction(
    data: bytes,
    media_type: str,
    *,
    gif_extractor: FrameExtractor = extract_gif,
    tgs_extractor: FrameExtractor = extract_tgs,
    video_extractor: FrameExtractor = extract_video,
) -> list[bytes]:
    """Выбирает декодер по формату анимации."""
    if media_type == "gif":
        return gif_extractor(data)

    if media_type == "tgs":
        return tgs_extractor(data)

    if media_type in ("webm", "mp4", "video"):
        return video_extractor(data)

    msg = f"Unsupported animation format: {media_type}"
    raise ValueError(msg)
