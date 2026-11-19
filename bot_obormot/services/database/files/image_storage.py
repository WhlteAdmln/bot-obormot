# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Low-level operations on image files in chat history."""

import base64
import re
from pathlib import Path

_MANAGED_NAME = re.compile(r"[0-9a-f]{32}\.jpg")


def is_managed_image(path: Path, images_dir: Path) -> bool:
    """Return True if the file is directly inside images_dir and has a managed name."""
    try:
        return (
            path.resolve().parent == images_dir.resolve()
            and _MANAGED_NAME.fullmatch(path.name) is not None
        )
    except OSError:
        return False


def read_image_as_base64(image_path: Path, mime_type: str) -> str:
    """Read an image and convert it to a Data URL."""
    image_data = image_path.read_bytes()
    encoded = base64.b64encode(image_data).decode("ascii")

    return f"data:{mime_type};base64,{encoded}"


def save_image(image_path: Path, image_data: bytes) -> None:
    """Write image bytes to a file."""
    image_path.write_bytes(image_data)


def delete_image(image_path: Path) -> None:
    """Delete an image file without raising if it is missing."""
    image_path.unlink(missing_ok=True)


def list_image_files(images_dir: Path) -> list[Path]:
    """Return the immediate contents of the image directory."""
    return list(images_dir.iterdir())
