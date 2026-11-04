"""Ограничения обработки изображений Telegram."""

MAX_IMAGE_DIMENSION = 1536
MAX_IMAGE_PIXELS = 40_000_000

MAX_GIF_PIXELS = 16_000_000  # ширина × высота холста GIF
MAX_GIF_FRAMES = 2000  # максимальное число кадров GIF
MAX_CONCURRENT_IMAGE_JOBS = 3  # одновременно обрабатываемые изображения
