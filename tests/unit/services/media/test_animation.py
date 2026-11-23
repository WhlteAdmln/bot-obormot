# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media animation."""

import sys

import pytest

from bot_obormot.errors import MediaError
from bot_obormot.services.media.animation import extract_animation_frames, tgs
from bot_obormot.services.media.texts import TGS_SUPPORT_UNAVAILABLE
from tests.support.tgs import valid_tgs


@pytest.fixture(autouse=True)
def _reset_warning_cache() -> None:
    """Allow every test to observe the one-time warning."""
    tgs._warn_tgs_unavailable.cache_clear()


@pytest.mark.asyncio
async def test_animation_pipeline_passes_the_polite_error_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public animation API does not wrap the polite message."""
    monkeypatch.setitem(sys.modules, "rlottie_python", None)

    with pytest.raises(MediaError, match=TGS_SUPPORT_UNAVAILABLE):
        await extract_animation_frames(valid_tgs(), "tgs")
