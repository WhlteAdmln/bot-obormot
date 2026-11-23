# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for animation tgs."""

import gzip
import io
import json
import logging
import os
import sys
from contextlib import AbstractContextManager, nullcontext
from types import SimpleNamespace

import pytest
from PIL import Image

from bot_obormot.errors import MediaError
from bot_obormot.services.media.animation import tgs
from bot_obormot.services.media.texts import TGS_SUPPORT_UNAVAILABLE
from tests.support.tgs import valid_tgs


@pytest.fixture(autouse=True)
def _reset_warning_cache() -> None:
    """Allow every test to observe the one-time warning."""
    # pylint: disable-next=protected-access  # the one-time warning has no reset API
    tgs._warn_tgs_unavailable.cache_clear()  # noqa: SLF001


def test_missing_decoder_gives_a_polite_media_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing optional module is reported with a user-facing message."""
    monkeypatch.setitem(sys.modules, "rlottie_python", None)

    with pytest.raises(MediaError, match=TGS_SUPPORT_UNAVAILABLE):
        tgs.extract_tgs(valid_tgs())


def test_missing_decoder_warns_only_once(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The log warning about the missing extra is written one time."""
    monkeypatch.setitem(sys.modules, "rlottie_python", None)

    with caplog.at_level(logging.WARNING, logger=tgs.logger.name):
        for _ in range(3):
            with pytest.raises(MediaError):
                tgs.extract_tgs(valid_tgs())

    expected_fragment = "bot-obormot[tgs]"
    warnings = [record for record in caplog.records if expected_fragment in record.msg]
    assert len(warnings) == 1


def test_invalid_file_is_still_rejected_before_the_import_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation errors keep priority over the missing-extra message."""
    monkeypatch.setitem(sys.modules, "rlottie_python", None)

    with pytest.raises(MediaError) as error:
        tgs.extract_tgs(b"not-a-gzip-file")

    assert str(error.value) != TGS_SUPPORT_UNAVAILABLE


def test_support_check_follows_the_installed_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The doctor helper reports whether the optional module can be found."""
    monkeypatch.setitem(sys.modules, "rlottie_python", None)
    assert tgs.tgs_support_available() is False


def test_validate_tgs_accepts_bounded_gzip_json() -> None:
    """Validate tgs accepts bounded gzip json."""
    data = gzip.compress(json.dumps({"w": 512, "h": 512}).encode("utf-8"))

    tgs.validate_tgs(data)


def test_validate_tgs_rejects_gzip_decompression_bomb() -> None:
    """Validate tgs rejects gzip decompression bomb."""
    data = gzip.compress(b"0" * (tgs.MAX_TGS_JSON + 1))

    with pytest.raises(MediaError, match="после распаковки"):
        tgs.validate_tgs(data)


def test_validate_tgs_rejects_compressed_data_over_limit() -> None:
    """Validate tgs rejects compressed data over limit."""
    data = os.urandom(tgs.MAX_TGS_COMPRESSED + 1)

    with pytest.raises(MediaError, match="Стикер слишком большой"):
        tgs.validate_tgs(data)


def test_validate_tgs_rejects_invalid_gzip_and_trailing_data() -> None:
    """Validate tgs rejects invalid gzip and trailing data."""
    with pytest.raises(MediaError, match="Некорректный файл"):
        tgs.validate_tgs(b"not-a-gzip-file")

    valid = gzip.compress(json.dumps({"w": 512, "h": 512}).encode("utf-8"))
    with pytest.raises(MediaError, match="Некорректный файл"):
        tgs.validate_tgs(valid + b"trailing-data")
    with pytest.raises(MediaError, match="Некорректный файл"):
        tgs.validate_tgs(valid[:-3])


@pytest.mark.parametrize(
    "document",
    [
        {"w": 0, "h": 512},
        {"w": 1025, "h": 512},
        {"w": 512, "h": -1},
        {"w": True, "h": 512},
        {"w": 512.0, "h": 512},
        [512, 512],
    ],
)
def test_validate_tgs_rejects_invalid_canvas(document: object) -> None:
    """Validate tgs rejects invalid canvas."""
    data = gzip.compress(json.dumps(document).encode("utf-8"))

    with pytest.raises(MediaError, match="размер анимации"):
        tgs.validate_tgs(data)


def test_extract_tgs_validates_before_importing_rlottie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extract tgs validates before importing rlottie."""
    imported_modules: list[str] = []
    monkeypatch.setattr(tgs.importlib, "import_module", imported_modules.append)

    with pytest.raises(MediaError, match="Некорректный файл"):
        tgs.extract_tgs(b"not-a-gzip-file")

    assert not imported_modules


def test_extract_tgs_imports_rlottie_for_valid_animation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extract tgs imports rlottie for valid animation."""

    def get_total_frames() -> int:
        return 1

    def render_frame(frame_num: int) -> Image.Image:
        _ = frame_num  # Passed by keyword; this fake ignores it.
        return Image.new("RGB", (1, 1))

    fake_animation = SimpleNamespace(
        lottie_animation_get_totalframe=get_total_frames,
        render_pillow_frame=render_frame,
    )

    def fake_from_tgs(_path: str) -> AbstractContextManager[SimpleNamespace]:
        return nullcontext(fake_animation)

    imports: list[str] = []

    def fake_import_module(name: str) -> SimpleNamespace:
        imports.append(name)
        return SimpleNamespace(
            LottieAnimation=SimpleNamespace(from_tgs=fake_from_tgs),
        )

    monkeypatch.setattr(tgs.importlib, "import_module", fake_import_module)
    data = gzip.compress(json.dumps({"w": 512, "h": 512}).encode("utf-8"))

    frames = tgs.extract_tgs(data)

    assert imports == ["rlottie_python"]
    assert len(frames) == 1
    with Image.open(io.BytesIO(frames[0])) as image:
        expected_format = "JPEG"
        assert image.format == expected_format
