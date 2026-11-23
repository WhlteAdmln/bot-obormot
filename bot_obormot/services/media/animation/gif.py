# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Frame extraction from GIF animations."""

import io

from PIL import Image

from bot_obormot.errors import MediaError
from bot_obormot.services.media.animation.jpeg import image_to_bytes
from bot_obormot.services.media.animation.sampling import sample_frame_indices
from bot_obormot.services.media.limits import MAX_GIF_FRAMES, MAX_GIF_PIXELS
from bot_obormot.services.media.safety import check_image_size
from bot_obormot.services.media.texts import GIF_TOO_MANY_FRAMES, IMAGE_TOO_LARGE


def _sample_frames(data: bytes) -> list[bytes]:
    """Decode evenly spaced GIF frames, enforcing the size and frame limits."""
    with Image.open(io.BytesIO(data)) as animation:
        # The logical canvas size is available before frame decoding.
        check_image_size(animation, MAX_GIF_PIXELS)

        total = getattr(animation, "n_frames", 1)

        if total <= 0:
            msg = "GIF does not contain frames"
            raise ValueError(msg)

        if total > MAX_GIF_FRAMES:
            msg = GIF_TOO_MANY_FRAMES
            raise MediaError(msg)

        indices = sample_frame_indices(total)
        frames = []

        for index in indices:
            animation.seek(index)
            frame = animation.convert("RGBA").copy()
            frames.append(image_to_bytes(frame))

        return frames


def extract_gif(data: bytes) -> list[bytes]:
    """Extract evenly spaced GIF frames using Pillow."""
    try:
        return _sample_frames(data)

    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        msg = IMAGE_TOO_LARGE
        raise MediaError(msg) from error
