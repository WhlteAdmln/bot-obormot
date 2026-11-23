# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Dispatch of animation decoding by media format."""

from collections.abc import Callable

from bot_obormot.services.media.animation.gif import extract_gif
from bot_obormot.services.media.animation.tgs import extract_tgs
from bot_obormot.services.media.animation.video import extract_video
from bot_obormot.services.media.media_types import MEDIA_TYPE_GIF, MEDIA_TYPE_TGS

FrameExtractor = Callable[[bytes], list[bytes]]


def dispatch_extraction(
    data: bytes,
    media_type: str,
    *,
    gif_extractor: FrameExtractor = extract_gif,
    tgs_extractor: FrameExtractor = extract_tgs,
    video_extractor: FrameExtractor = extract_video,
) -> list[bytes]:
    """Select the decoder based on the animation format."""
    if media_type == MEDIA_TYPE_GIF:
        return gif_extractor(data)

    if media_type == MEDIA_TYPE_TGS:
        return tgs_extractor(data)

    if media_type in {"webm", "mp4", "video"}:
        return video_extractor(data)

    msg = f"Unsupported animation format: {media_type}"
    raise ValueError(msg)
