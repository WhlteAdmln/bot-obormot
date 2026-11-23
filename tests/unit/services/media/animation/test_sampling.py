# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for animation sampling."""

import pytest

from bot_obormot.services.media.animation.sampling import sample_frame_indices


def test_sample_frame_indices_matches_even_sampling_and_limits_count() -> None:
    """Sample frame indices matches even sampling and limits count."""
    assert sample_frame_indices(1) == [0]
    assert sample_frame_indices(4) == [0, 1, 2, 3]
    assert sample_frame_indices(20) == [0, 4, 8, 11, 15, 19]


def test_sample_frame_indices_rejects_empty_animation() -> None:
    """Sample frame indices rejects empty animation."""
    with pytest.raises(ValueError, match="does not contain frames"):
        sample_frame_indices(0)
