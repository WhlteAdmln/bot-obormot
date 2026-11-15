# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Preparation of still images for the multimodal LLM request."""

import base64
import io

from PIL import Image, ImageOps

from bot.errors import MediaError
from bot.services.media.limits import MAX_IMAGE_DIMENSION, MAX_IMAGE_PIXELS


def prepare_image(image_data: bytes) -> str:
    """Преобразует изображение в JPEG Base64."""
    with Image.open(io.BytesIO(image_data)) as source:
        width, height = source.size

        if width * height > MAX_IMAGE_PIXELS:
            msg = (
                "Изображение имеет слишком большое разрешение "
                "(максимум 40 миллионов пикселей)."
            )
            raise MediaError(msg)

        image = ImageOps.exif_transpose(source)
        image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))

        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, "white")
            background.paste(
                image,
                mask=image.getchannel("A"),
            )
            image = background
        else:
            image = image.convert("RGB")

        output = io.BytesIO()
        image.save(output, format="JPEG", quality=85, optimize=True)

    encoded = base64.b64encode(output.getvalue()).decode("ascii")

    return f"data:image/jpeg;base64,{encoded}"
