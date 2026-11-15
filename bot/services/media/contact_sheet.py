# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Сборка кадров анимации в одно изображение для Vision-модели.

Контактный лист позволяет модели увидеть кадры как единую
последовательность, а не как независимые изображения.
"""

import io
import math

from PIL import Image, ImageDraw, ImageOps

from bot.services.media.animation.limits import MAX_FRAMES

CELL_WIDTH = 512
CELL_HEIGHT = 384
GRID_COLUMNS = 3
HEADER_HEIGHT = 36
IMAGE_PADDING = 12


def build_contact_sheet(frames: list[bytes]) -> bytes:
    """Объединяет до MAX_FRAMES изображений в один нумерованный JPEG.

    Порядок кадров сохраняется: слева направо, затем сверху вниз.
    Одно изображение возвращается без перекодирования.
    """
    if not frames:
        msg = "Cannot build a contact sheet without frames"
        raise ValueError(msg)

    if len(frames) == 1:
        return frames[0]

    if len(frames) > MAX_FRAMES:
        msg = f"Contact sheet supports at most {MAX_FRAMES} frames"
        raise ValueError(msg)

    columns = min(GRID_COLUMNS, len(frames))
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new(
        "RGB",
        (columns * CELL_WIDTH, rows * CELL_HEIGHT),
        color="white",
    )
    draw = ImageDraw.Draw(sheet)

    for index, frame_data in enumerate(frames):
        with Image.open(io.BytesIO(frame_data)) as source:
            frame = ImageOps.exif_transpose(source)
            frame.load()

            if frame.mode in ("RGBA", "LA") or "transparency" in frame.info:
                rgba = frame.convert("RGBA")
                normalized = Image.new("RGB", rgba.size, "white")
                normalized.paste(rgba, mask=rgba.getchannel("A"))
            else:
                normalized = frame.convert("RGB")

            normalized.thumbnail(
                (
                    CELL_WIDTH - 2 * IMAGE_PADDING,
                    CELL_HEIGHT - HEADER_HEIGHT - 2 * IMAGE_PADDING,
                ),
                Image.Resampling.LANCZOS,
            )

        column = index % columns
        row = index // columns
        left = column * CELL_WIDTH
        top = row * CELL_HEIGHT

        draw.text((left + IMAGE_PADDING, top + 10), f"FRAME {index + 1}", fill="black")

        image_left = left + (CELL_WIDTH - normalized.width) // 2
        image_top = (
            top + HEADER_HEIGHT + (CELL_HEIGHT - HEADER_HEIGHT - normalized.height) // 2
        )
        sheet.paste(normalized, (image_left, image_top))
        draw.rectangle(
            (left, top, left + CELL_WIDTH - 1, top + CELL_HEIGHT - 1),
            outline=(190, 190, 190),
            width=1,
        )

    output = io.BytesIO()
    sheet.save(output, format="JPEG", quality=88, optimize=True)
    return output.getvalue()
