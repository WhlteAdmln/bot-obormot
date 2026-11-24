# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media animation."""

import sys

import pytest

from bot_obormot.errors import MediaError
from bot_obormot.services.media.animation import extract_animation_frames
from bot_obormot.services.media.texts import TGS_SUPPORT_UNAVAILABLE
from tests.support.tgs import valid_tgs


@pytest.mark.asyncio
async def test_animation_pipeline_passes_the_polite_error_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "rlottie_python", None)

    with pytest.raises(MediaError, match=TGS_SUPPORT_UNAVAILABLE):
        await extract_animation_frames(valid_tgs(), "tgs")
