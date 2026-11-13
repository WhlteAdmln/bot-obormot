# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Проверки размеров изображений до их декодирования."""

import warnings

from PIL import Image

from bot.errors import MediaError
from bot.services.media.limits import MAX_IMAGE_PIXELS


def check_image_size(image: Image.Image, max_pixels: int) -> None:
    """Отклоняет изображение, если заявленный размер слишком велик."""
    width, height = image.size

    if width <= 0 or height <= 0 or width * height > max_pixels:
        msg = "Изображение слишком большое по размеру."
        raise MediaError(msg)


def configure_pillow_limits() -> None:
    """Включает встроенную защиту Pillow от decompression bombs."""
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)
