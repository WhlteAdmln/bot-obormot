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


def test_check_image_size_rejects_invalid_and_oversized_dimensions() -> None:
    """Check image size rejects invalid and oversized dimensions."""
    with pytest.raises(MediaError):
        check_image_size(SimpleNamespace(size=(0, 10)), 100)
    with pytest.raises(MediaError):
        check_image_size(SimpleNamespace(size=(11, 10)), 100)
    check_image_size(SimpleNamespace(size=(10, 10)), 100)


def test_configure_pillow_limits_sets_global_decompression_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configure pillow limits sets global decompression limit."""
    # Не оставляем глобальный warning filter изменённым для других тестов.
    monkeypatch.setattr(warnings, "filters", warnings.filters.copy())
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", None)
    configure_pillow_limits()
    assert Image.MAX_IMAGE_PIXELS == MAX_IMAGE_PIXELS
    expected_action = "error"
    assert any(
        action == expected_action and category is Image.DecompressionBombWarning
        for action, _message, category, _module, _lineno in warnings.filters
    )
