# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Frame extraction from GIF animations."""

import io

from PIL import Image

from bot.errors import MediaError
from bot.services.media.animation.jpeg import image_to_bytes
from bot.services.media.animation.sampling import sample_frame_indices
from bot.services.media.limits import MAX_GIF_FRAMES, MAX_GIF_PIXELS
from bot.services.media.safety import check_image_size


def extract_gif(data: bytes) -> list[bytes]:
    """Извлекает равномерно распределённые кадры GIF через Pillow."""
    try:
        with Image.open(io.BytesIO(data)) as animation:
            # Размер логического холста известен до декодирования кадров.
            check_image_size(animation, MAX_GIF_PIXELS)

            total = getattr(animation, "n_frames", 1)

            if total <= 0:
                msg = "GIF does not contain frames"
                raise ValueError(msg)

            if total > MAX_GIF_FRAMES:
                msg = "В GIF слишком много кадров."
                raise MediaError(msg)

            indices = sample_frame_indices(total)
            frames = []

            for index in indices:
                animation.seek(index)
                frame = animation.convert("RGBA").copy()
                frames.append(image_to_bytes(frame))

            return frames

    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        msg = "Изображение слишком большое по размеру."
        raise MediaError(msg) from error
