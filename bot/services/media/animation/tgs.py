# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Safely validate and extract frames from Telegram TGS stickers."""

import importlib
import json
import tempfile
import zlib
from pathlib import Path

from bot.errors import MediaError
from bot.services.media.animation.jpeg import image_to_bytes
from bot.services.media.animation.sampling import sample_frame_indices
from bot.services.media.texts import (
    TGS_INVALID_CONTENT,
    TGS_INVALID_FILE,
    TGS_INVALID_SIZE,
    TGS_TOO_LARGE_AFTER_DECOMPRESSION,
    TGS_TOO_LARGE_OR_EMPTY,
)

# Telegram limits TGS file size; leave room for valid stickers.
MAX_TGS_COMPRESSED = 256 * 1024
MAX_TGS_JSON = 4 * 1024 * 1024
MAX_TGS_SIDE = 1024


def validate_tgs(data: bytes) -> None:
    """Validate gzip, JSON size, and canvas before passing data to rlottie."""
    if not data or len(data) > MAX_TGS_COMPRESSED:
        msg = TGS_TOO_LARGE_OR_EMPTY
        raise MediaError(msg)

    decompressor = zlib.decompressobj(wbits=31)  # 31 = gzip

    try:
        # +1 distinguishes the exact size limit from an oversized payload
        # without decompressing the entire potentially huge stream.
        raw = decompressor.decompress(data, MAX_TGS_JSON + 1)
    except zlib.error as error:
        msg = TGS_INVALID_FILE
        raise MediaError(msg) from error

    if len(raw) > MAX_TGS_JSON or decompressor.unconsumed_tail:
        msg = TGS_TOO_LARGE_AFTER_DECOMPRESSION
        raise MediaError(msg)

    if not decompressor.eof:
        msg = TGS_INVALID_FILE
        raise MediaError(msg)

    # Reject trailing data and concatenated gzip streams.
    if decompressor.unused_data:
        msg = TGS_INVALID_FILE
        raise MediaError(msg)

    try:
        document = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        msg = TGS_INVALID_CONTENT
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
        msg = TGS_INVALID_SIZE
        raise MediaError(msg)


def extract_tgs(data: bytes) -> list[bytes]:
    """Validate TGS and extract evenly distributed frames."""
    validate_tgs(data)

    # rlottie is a native decoder. Import it only after validation so
    # malformed and oversized data never reaches it.
    rlottie_module = importlib.import_module("rlottie_python")
    lottie_animation_class = rlottie_module.LottieAnimation

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
