# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Безопасная проверка и извлечение кадров Telegram TGS."""

import importlib
import json
import tempfile
import zlib
from pathlib import Path

from bot.errors import MediaError
from bot.services.media.animation.jpeg import image_to_bytes
from bot.services.media.animation.sampling import sample_frame_indices

# Telegram ограничивает размер TGS; оставляем запас на допустимые стикеры.
MAX_TGS_COMPRESSED = 256 * 1024
MAX_TGS_JSON = 4 * 1024 * 1024
MAX_TGS_SIDE = 1024


def validate_tgs(data: bytes) -> None:
    """Проверяет gzip, размер JSON и холст до передачи данных в rlottie."""
    if not data or len(data) > MAX_TGS_COMPRESSED:
        msg = "Стикер слишком большой или пустой."
        raise MediaError(msg)

    decompressor = zlib.decompressobj(wbits=31)  # 31 = gzip

    try:
        # +1 позволяет отличить ровно допустимый размер от превышения лимита,
        # не распаковывая весь потенциально огромный поток.
        raw = decompressor.decompress(data, MAX_TGS_JSON + 1)
    except zlib.error as error:
        msg = "Некорректный файл стикера."
        raise MediaError(msg) from error

    if len(raw) > MAX_TGS_JSON or decompressor.unconsumed_tail:
        msg = "Стикер слишком большой после распаковки."
        raise MediaError(msg)

    if not decompressor.eof:
        msg = "Некорректный файл стикера."
        raise MediaError(msg)

    # Не принимаем дополнительные данные и несколько склеенных gzip-потоков.
    if decompressor.unused_data:
        msg = "Некорректный файл стикера."
        raise MediaError(msg)

    try:
        document = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        msg = "Некорректное содержимое стикера."
        raise MediaError(msg) from error

    width = document.get("w") if isinstance(document, dict) else None
    height = document.get("h") if isinstance(document, dict) else None

    valid_size = (
        type(width) is int
        and type(height) is int
        and 0 < width <= MAX_TGS_SIDE
        and 0 < height <= MAX_TGS_SIDE
    )

    if not valid_size:
        msg = "Недопустимый размер анимации стикера."
        raise MediaError(msg)


def extract_tgs(data: bytes) -> list[bytes]:
    """Проверяет TGS и извлекает равномерно распределённые кадры."""
    validate_tgs(data)

    # rlottie — нативный декодер. Импортируем его только после проверки,
    # чтобы некорректные и чрезмерно большие данные до него не доходили.
    lottie_animation_class = importlib.import_module("rlottie_python").LottieAnimation

    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "sticker.tgs"
        path.write_bytes(data)

        with lottie_animation_class.from_tgs(str(path)) as animation:
            total = animation.lottie_animation_get_totalframe()

            if total <= 0:
                msg = "TGS animation has no frames"
                raise ValueError(msg)

            indices = sample_frame_indices(total)
            frames = []

            for index in indices:
                image = animation.render_pillow_frame(frame_num=index)
                frames.append(image_to_bytes(image))

            return frames
