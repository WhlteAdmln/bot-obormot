# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media safety."""

import warnings
from types import SimpleNamespace

import pytest
from PIL import Image

from bot_obormot.errors import MediaError
from bot_obormot.services.media.limits import MAX_IMAGE_PIXELS
from bot_obormot.services.media.safety import check_image_size, configure_pillow_limits
from bot_obormot.services.media.texts import IMAGE_TOO_LARGE


def _rejection(size: tuple[int, int], max_pixels: int) -> str:
    try:
        check_image_size(SimpleNamespace(size=size), max_pixels)
    except MediaError as error:
        return str(error)
    return ""


@pytest.fixture(name="pillow_state")
def fixture_pillow_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Restore the global Pillow limit and warning filters after the test."""
    monkeypatch.setattr(warnings, "filters", warnings.filters.copy())
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", None)


@pytest.mark.parametrize(
    ("size", "max_pixels"),
    [((11, 10), 100), ((101, 1), 100), ((1, 3), 2), ((2, 2), 0), ((65535, 65535), 40)],
    ids=["area", "wide-strip", "tall-strip", "zero-limit", "huge-canvas"],
)
def test_check_image_size_rejects_an_image_over_the_pixel_limit(
    size: tuple[int, int], max_pixels: int
) -> None:
    assert _rejection(size, max_pixels) == IMAGE_TOO_LARGE, (
        "an oversized image must be refused"
    )


@pytest.mark.parametrize(
    ("size", "max_pixels"),
    [((10, 10), 100), ((1, 1), 1), ((100, 1), 100)],
    ids=["exact-area", "single-pixel", "exact-strip"],
)
def test_check_image_size_accepts_an_image_at_the_pixel_limit(
    size: tuple[int, int], max_pixels: int
) -> None:
    expected_empty = ""
    assert _rejection(size, max_pixels) == expected_empty, "an image at the limit"


@pytest.mark.parametrize(
    "size",
    [(0, 10), (10, 0), (-3, 4), (5, -1), (-7, -7)],
    ids=[
        "zero-width",
        "zero-height",
        "negative-width",
        "negative-height",
        "both-negative",
    ],
)
def test_check_image_size_rejects_a_declared_size_that_is_not_positive(
    size: tuple[int, int],
) -> None:
    assert _rejection(size, 1000) == IMAGE_TOO_LARGE, (
        "a non-positive size must be refused"
    )


@pytest.mark.usefixtures("pillow_state")
def test_configure_pillow_limits_sets_the_global_pixel_limit() -> None:
    configure_pillow_limits()
    assert Image.MAX_IMAGE_PIXELS == MAX_IMAGE_PIXELS, "Pillow has the wrong limit"


@pytest.mark.usefixtures("pillow_state")
def test_configure_pillow_limits_turns_bomb_warnings_into_errors() -> None:
    configure_pillow_limits()
    actions = [
        action
        for action, _message, category, _module, _lineno in warnings.filters
        if category is Image.DecompressionBombWarning
    ]
    expected = "error"
    assert actions[:1] == [expected], "a bomb warning must raise an error"
