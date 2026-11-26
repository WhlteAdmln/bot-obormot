# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for animation sampling."""

import pytest

from bot_obormot.services.media.animation.sampling import sample_frame_indices


@pytest.mark.parametrize(
    ("frame_count", "expected"),
    [
        (1, [0]),
        (4, [0, 1, 2, 3]),
        (20, [0, 4, 8, 11, 15, 19]),
    ],
)
def test_sample_frame_indices_matches_even_sampling_and_limits_count(
    frame_count: int, expected: list[int]
) -> None:
    assert sample_frame_indices(frame_count) == expected, "the frames were missampled"


def test_sample_frame_indices_rejects_empty_animation() -> None:
    frame_count = 0
    expected = "Animation does not contain frames"
    with pytest.raises(ValueError, match="does not contain frames") as caught:
        sample_frame_indices(frame_count)
    assert str(caught.value) == expected, "an empty animation was not rejected"
