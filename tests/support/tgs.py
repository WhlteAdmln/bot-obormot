# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Shared helpers for small split tests."""

import gzip
import json


def valid_tgs() -> bytes:
    """Build a minimal valid TGS payload."""
    return gzip.compress(json.dumps({"w": 512, "h": 512}).encode("utf-8"))
