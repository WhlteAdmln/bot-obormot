# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for database image storage."""

import base64
from pathlib import Path

import pytest

from bot_obormot.services.database.files.image_storage import (
    delete_image,
    is_managed_image,
    list_image_files,
    read_image_as_base64,
    save_image,
)

MANAGED_NAME = "3f2b9c0d4e5a46b7a8c9d0e1f2a3b4c5.jpg"


@pytest.fixture(name="images_dir")
def fixture_images_dir(tmp_path: Path) -> Path:
    """Create an image directory with one nested directory."""
    path = tmp_path / "images"
    (path / "nested").mkdir(parents=True)
    return path


def test_read_image_as_base64_returns_a_data_url(tmp_path: Path) -> None:
    image_path = tmp_path / "image.jpg"
    image_path.write_bytes(b"\xff\xd8\xff\x00raw")
    expected = "data:image/jpeg;base64," + base64.b64encode(
        b"\xff\xd8\xff\x00raw"
    ).decode("ascii")
    assert read_image_as_base64(image_path, "image/jpeg") == expected, (
        "the data URL is wrong"
    )


def test_save_image_writes_the_bytes(tmp_path: Path) -> None:
    image_path = tmp_path / MANAGED_NAME
    save_image(image_path, b"\x00jpeg\xff")
    expected = b"\x00jpeg\xff"
    assert image_path.read_bytes() == expected, "the saved bytes differ"


def test_delete_image_removes_the_file(tmp_path: Path) -> None:
    image_path = tmp_path / MANAGED_NAME
    image_path.write_bytes(b"old")
    delete_image(image_path)
    assert not image_path.exists(), "the image must be deleted"


def test_delete_image_ignores_a_missing_file(tmp_path: Path) -> None:
    image_path = tmp_path / MANAGED_NAME
    delete_image(image_path)
    assert not image_path.exists(), "deleting a missing image must stay quiet"


def test_list_image_files_returns_direct_children(images_dir: Path) -> None:
    first = images_dir / "first.jpg"
    first.write_bytes(b"1")
    (images_dir / "nested" / "deep.jpg").write_bytes(b"2")
    expected = {first, images_dir / "nested"}
    assert set(list_image_files(images_dir)) == expected, "only direct children"


def test_is_managed_image_accepts_a_uuid_jpg_in_the_directory(
    images_dir: Path,
) -> None:
    assert is_managed_image(images_dir / MANAGED_NAME, images_dir) is True, (
        "a managed name directly in the directory must pass"
    )


@pytest.mark.parametrize(
    "relative",
    [
        "notes.txt",
        "3F2B9C0D4E5A46B7A8C9D0E1F2A3B4C5.jpg",
        "3f2b9c0d4e5a46b7a8c9d0e1f2a3b4c.jpg",
        f"{MANAGED_NAME}.exe",
        "3f2b9c0d-4e5a-46b7-a8c9-d0e1f2a3b4c5.jpg",
        f"nested/{MANAGED_NAME}",
        f"../{MANAGED_NAME}",
        f"nested/../../{MANAGED_NAME}",
        "../../etc/passwd",
    ],
    ids=[
        "other-name",
        "upper-case",
        "short-hex",
        "double-extension",
        "dashed-uuid",
        "nested",
        "parent",
        "traversal",
        "system-file",
    ],
)
def test_is_managed_image_rejects_foreign_paths(
    images_dir: Path, relative: str
) -> None:
    assert is_managed_image(images_dir / relative, images_dir) is False, (
        "a path outside the managed set must be refused"
    )


def test_is_managed_image_rejects_a_symlink_to_a_file_outside(
    tmp_path: Path, images_dir: Path
) -> None:
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"private")
    link = images_dir / MANAGED_NAME
    link.symlink_to(outside)
    assert is_managed_image(link, images_dir) is False, (
        "a symlink that leaves the directory must be refused"
    )
