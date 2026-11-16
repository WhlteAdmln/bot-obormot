# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Limits for processing Telegram images."""

MAX_IMAGE_DIMENSION = 1536
MAX_IMAGE_PIXELS = 40_000_000

MAX_GIF_PIXELS = 16_000_000  # GIF canvas width × height
MAX_GIF_FRAMES = 2000  # Maximum number of GIF frames
MAX_CONCURRENT_IMAGE_JOBS = 3  # Number of images processed concurrently
