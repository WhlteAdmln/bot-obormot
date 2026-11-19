# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Thresholds and timing settings for message aggregation."""

# Minimum first-part length required to start aggregation.
MESSAGE_LENGTH_THRESHOLD = 3000

# Maximum wait time for the next message part.
MESSAGE_AGGREGATION_WINDOW = 3.0
