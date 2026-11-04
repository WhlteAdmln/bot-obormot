"""Низкоуровневые операции с файлами изображений истории."""

import base64
from pathlib import Path


def read_image_as_base64(image_path: Path, mime_type: str) -> str:
    """Читает изображение и преобразует его в Data URL."""
    image_data = image_path.read_bytes()
    encoded = base64.b64encode(image_data).decode("ascii")

    return f"data:{mime_type};base64,{encoded}"


def save_image(image_path: Path, image_data: bytes) -> None:
    """Записывает байты изображения в файл."""
    image_path.write_bytes(image_data)


def delete_image(image_path: Path) -> None:
    """Удаляет файл изображения, не считая его отсутствие ошибкой."""
    image_path.unlink(missing_ok=True)


def list_image_files(images_dir: Path) -> list[Path]:
    """Возвращает непосредственное содержимое каталога изображений."""
    return list(images_dir.iterdir())
