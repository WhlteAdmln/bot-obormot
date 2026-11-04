import base64

from bot.services.database.files.image_storage import (
    delete_image,
    list_image_files,
    read_image_as_base64,
    save_image,
)


def test_read_image_as_base64_returns_data_url(tmp_path):
    image_path = tmp_path / "image.jpg"
    image_data = b"image-bytes"
    image_path.write_bytes(image_data)

    result = read_image_as_base64(image_path, "image/jpeg")

    expected = base64.b64encode(image_data).decode("ascii")
    assert result == f"data:image/jpeg;base64,{expected}"


def test_save_and_delete_image(tmp_path):
    image_path = tmp_path / "image.jpg"
    image_data = b"new-image"

    save_image(image_path, image_data)
    assert image_path.read_bytes() == image_data

    delete_image(image_path)
    assert not image_path.exists()

    # Повторное удаление должно оставаться безопасным (missing_ok=True).
    delete_image(image_path)


def test_list_image_files_returns_direct_children(tmp_path):
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"1")
    second.write_bytes(b"2")
    (tmp_path / "nested").mkdir()

    result = list_image_files(tmp_path)

    assert set(result) == {first, second, tmp_path / "nested"}
