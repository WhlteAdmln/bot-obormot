# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for database image storage."""

import base64
import uuid
from pathlib import Path

from bot.services.database.files.image_storage import (
    delete_image,
    is_managed_image,
    list_image_files,
    read_image_as_base64,
    save_image,
)


def test_read_image_as_base64_returns_data_url(tmp_path: Path) -> None:
    """Read image as base64 returns data url."""
    image_path = tmp_path / "image.jpg"
    image_data = b"image-bytes"
    image_path.write_bytes(image_data)

    result = read_image_as_base64(image_path, "image/jpeg")

    expected = base64.b64encode(image_data).decode("ascii")
    assert result == f"data:image/jpeg;base64,{expected}"


def test_save_and_delete_image(tmp_path: Path) -> None:
    """Save and delete image."""
    image_path = tmp_path / "image.jpg"
    image_data = b"new-image"

    save_image(image_path, image_data)
    assert image_path.read_bytes() == image_data

    delete_image(image_path)
    assert not image_path.exists()

    # Повторное удаление должно оставаться безопасным (missing_ok=True).
    delete_image(image_path)


def test_list_image_files_returns_direct_children(tmp_path: Path) -> None:
    """List image files returns direct children."""
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"1")
    second.write_bytes(b"2")
    (tmp_path / "nested").mkdir()

    result = list_image_files(tmp_path)

    assert set(result) == {first, second, tmp_path / "nested"}


def test_is_managed_image_requires_uuid_jpg_directly_in_images_dir(
    tmp_path: Path,
) -> None:
    """Is managed image requires uuid jpg directly in images dir."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    valid = images_dir / f"{uuid.uuid4().hex}.jpg"
    invalid_name = images_dir / "notes.txt"
    nested_dir = images_dir / "nested"
    nested_dir.mkdir()
    nested = nested_dir / f"{uuid.uuid4().hex}.jpg"
    outside = tmp_path / f"{uuid.uuid4().hex}.jpg"

    assert is_managed_image(valid, images_dir) is True
    assert is_managed_image(invalid_name, images_dir) is False
    assert is_managed_image(nested, images_dir) is False
    assert is_managed_image(outside, images_dir) is False
