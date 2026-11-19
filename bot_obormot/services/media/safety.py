# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Image size checks before decoding."""

import warnings

from PIL import Image

from bot_obormot.errors import MediaError
from bot_obormot.services.media.limits import MAX_IMAGE_PIXELS
from bot_obormot.services.media.texts import IMAGE_TOO_LARGE


def check_image_size(image: Image.Image, max_pixels: int) -> None:
    """Reject an image if its declared dimensions exceed the limit."""
    width, height = image.size

    if width <= 0 or height <= 0 or width * height > max_pixels:
        msg = IMAGE_TOO_LARGE
        raise MediaError(msg)


def configure_pillow_limits() -> None:
    """Enable Pillow's built-in protection against decompression bombs."""
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)
