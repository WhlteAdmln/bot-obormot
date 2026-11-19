# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Constants for calculating the available LLM context."""

CONTEXT_SAFETY_MARGIN = 512
# Reserve an additional 15% of the context when estimating token counts.
ESTIMATE_CONTEXT_SAFETY_FACTOR = 0.15
# Estimated context reserve for each image_url part.
IMAGE_TOKEN_RESERVE = 2048
