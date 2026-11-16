# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""User-facing media messages and LLM instructions."""

ANIMATION_CONTACT_SHEET_INSTRUCTION = (
    "\n\nКадры собраны в одно нумерованное изображение-монтаж. "
    "Просматривай их по порядку: слева направо, сверху вниз, "
    "и рассматривай как последовательность одной анимации."
)
MULTIPLE_FRAMES_INSTRUCTION = (
    "\n\nКадры расположены в хронологическом порядке. "
    "Рассматривай их как последовательность одной анимации."
)

ANIMATION_MEDIA_PROMPT = (
    "Посмотри на последовательность кадров этой анимации. "
    "Опиши, что происходит, какие движения и эмоции "
    "ты замечаешь."
)
STICKER_MEDIA_PROMPT = "Посмотри на стикер и опиши его."
IMAGE_MEDIA_PROMPT = "Посмотри на изображение и опиши, что на нём изображено."

GIF_TOO_MANY_FRAMES = "В GIF слишком много кадров."
IMAGE_TOO_LARGE = "Изображение слишком большое по размеру."
_IMAGE_RESOLUTION_PREFIX = "Изображение имеет слишком большое разрешение"
_IMAGE_RESOLUTION_SUFFIX = "(максимум 40 миллионов пикселей)."
IMAGE_RESOLUTION_TOO_LARGE = f"{_IMAGE_RESOLUTION_PREFIX} {_IMAGE_RESOLUTION_SUFFIX}"
MEDIA_TYPE_MISMATCH = "Тип файла не совпадает с его содержимым."
UNSUPPORTED_OR_DAMAGED_MEDIA_FILE = "Неподдерживаемый или повреждённый файл."
TGS_INVALID_CONTENT = "Некорректное содержимое стикера."
TGS_INVALID_FILE = "Некорректный файл стикера."
TGS_INVALID_SIZE = "Недопустимый размер анимации стикера."
TGS_TOO_LARGE_AFTER_DECOMPRESSION = "Стикер слишком большой после распаковки."
TGS_TOO_LARGE_OR_EMPTY = "Стикер слишком большой или пустой."
UNSUPPORTED_VIDEO_FORMAT = "Неподдерживаемый формат видео."
VIDEO_RESOLUTION_TOO_LARGE = "Разрешение исходного видео слишком большое."
