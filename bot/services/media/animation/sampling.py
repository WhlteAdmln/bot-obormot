# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Uniform sampling of animation frame indices."""

from bot.services.media.animation.limits import MAX_FRAMES


def sample_frame_indices(total_frames: int) -> list[int]:
    """Return evenly distributed frame indices."""
    if total_frames <= 0:
        msg = "Animation does not contain frames"
        raise ValueError(msg)

    count = min(MAX_FRAMES, total_frames)

    if count == 1:
        return [0]

    return [round(index * (total_frames - 1) / (count - 1)) for index in range(count)]
