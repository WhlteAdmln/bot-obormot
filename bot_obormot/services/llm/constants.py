# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Constants for calculating the available LLM context."""

CONTEXT_SAFETY_MARGIN = 512
# Reserve an additional 15% of the context when estimating token counts.
ESTIMATE_CONTEXT_SAFETY_FACTOR = 0.15
# Estimated context reserve for each image_url part.
IMAGE_TOKEN_RESERVE = 2048

# Roles of chat messages in the OpenAI-compatible API.
ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
# Types of message content parts.
PART_TYPE_TEXT = "text"
PART_TYPE_IMAGE_URL = "image_url"
# Values of the LLM_TOKEN_COUNTING setting and the detected counting mode.
COUNTING_MODE_AUTO = "auto"
COUNTING_MODE_ESTIMATE = "estimate"
# The finish reason reported when generation stops at the max_tokens limit.
FINISH_REASON_LENGTH = "length"
