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
from bot_obormot.services.media.texts import (
    TGS_INVALID_CONTENT,
    TGS_INVALID_FILE,
    TGS_INVALID_SIZE,
    TGS_SUPPORT_UNAVAILABLE,
    TGS_TOO_LARGE_AFTER_DECOMPRESSION,
    TGS_TOO_LARGE_OR_EMPTY,
)
from tests.support.tgs import valid_tgs


def _rejection(data: bytes) -> str:
    try:
        tgs.validate_tgs(data)
    except MediaError as error:
        return str(error)
    return ""


def _extraction_error(data: bytes) -> str:
    try:
        tgs.extract_tgs(data)
    except MediaError as error:
        return str(error)
    return ""


def _gzip_json(document: object) -> bytes:
    return gzip.compress(json.dumps(document).encode("utf-8"))


def _fake_rlottie(imports: list[str]) -> object:
    def get_total_frames() -> int:
        return 1

    def render_frame(frame_num: int) -> Image.Image:
        return Image.new("RGB", (1 + frame_num, 1))

    animation = SimpleNamespace(
        lottie_animation_get_totalframe=get_total_frames,
        render_pillow_frame=render_frame,
    )

    def from_tgs(_path: str) -> AbstractContextManager[SimpleNamespace]:
        return nullcontext(animation)

    def import_module(name: str) -> SimpleNamespace:
        imports.append(name)
        return SimpleNamespace(LottieAnimation=SimpleNamespace(from_tgs=from_tgs))

    return import_module


@pytest.fixture(name="no_decoder")
def fixture_no_decoder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hide the optional rlottie decoder."""
    monkeypatch.setitem(sys.modules, "rlottie_python", None)


@pytest.mark.usefixtures("no_decoder")
def test_missing_decoder_gives_a_polite_media_error() -> None:
    assert _extraction_error(valid_tgs()) == TGS_SUPPORT_UNAVAILABLE, (
        "a missing decoder must give the polite message"
    )


@pytest.mark.usefixtures("no_decoder")
def test_startup_check_warns_when_decoder_is_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger=tgs.logger.name):
        tgs.log_tgs_support()
    hint = "bot-obormot[tgs]"
    actual = [hint in record.getMessage() for record in caplog.records]
    expected = [True]
    assert actual == expected, "a missing decoder must be reported once at startup"


def test_startup_check_is_silent_when_decoder_is_installed(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(tgs, "tgs_support_available", lambda: True)
    with caplog.at_level(logging.DEBUG, logger=tgs.logger.name):
        tgs.log_tgs_support()
    expected: list[str] = []
    actual = [record.getMessage() for record in caplog.records]
    assert actual == expected, "an installed decoder must not produce log records"


@pytest.mark.usefixtures("no_decoder")
def test_missing_decoder_does_not_log_on_each_sticker(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger=tgs.logger.name):
        for _ in range(3):
            _extraction_error(valid_tgs())
    expected: list[str] = []
    actual = [record.getMessage() for record in caplog.records]
    assert actual == expected, "the missing extra is reported at startup only"


@pytest.mark.usefixtures("no_decoder")
def test_invalid_file_is_still_rejected_before_the_import_check() -> None:
    assert _extraction_error(b"not-a-gzip-file") == TGS_INVALID_FILE, (
        "an invalid file must be refused before the decoder check"
    )


@pytest.mark.usefixtures("no_decoder")
def test_support_check_follows_the_installed_module() -> None:
    assert tgs.tgs_support_available() is False, "a blocked module is not available"


@pytest.mark.parametrize(
    "document",
    [
        {"w": 512, "h": 512},
        {"w": 1, "h": 1},
        {"w": tgs.MAX_TGS_SIDE, "h": tgs.MAX_TGS_SIDE},
        {"w": 100, "h": 200, "layers": [], "nm": "\N{RIGHT-TO-LEFT OVERRIDE}evil"},
    ],
    ids=["regular", "smallest", "largest", "extra-keys"],
)
def test_validate_tgs_accepts_bounded_gzip_json(document: object) -> None:
    expected_empty = ""
    assert _rejection(_gzip_json(document)) == expected_empty, (
        "a bounded sticker must pass"
    )


@pytest.mark.parametrize(
    "data",
    [b"", b"\x1f" * (tgs.MAX_TGS_COMPRESSED + 1)],
    ids=["empty", "over-limit"],
)
def test_validate_tgs_rejects_empty_or_oversized_compressed_data(data: bytes) -> None:
    assert _rejection(data) == TGS_TOO_LARGE_OR_EMPTY, (
        "empty or oversized data must be refused before decompression"
    )


def test_validate_tgs_rejects_random_data_over_the_compressed_limit() -> None:
    data = os.urandom(tgs.MAX_TGS_COMPRESSED + 1)
    assert _rejection(data) == TGS_TOO_LARGE_OR_EMPTY, (
        "random data over the limit must be refused"
    )


@pytest.mark.parametrize(
    "size",
    [tgs.MAX_TGS_JSON + 1, tgs.MAX_TGS_JSON * 8],
    ids=["one-byte-over", "eight-times-over"],
)
def test_validate_tgs_rejects_a_gzip_decompression_bomb(size: int) -> None:
    data = gzip.compress(b"0" * size)
    assert _rejection(data) == TGS_TOO_LARGE_AFTER_DECOMPRESSION, (
        "a decompression bomb must be refused"
    )


@pytest.mark.parametrize(
    "data",
    [
        b"not-a-gzip-file",
        _gzip_json({"w": 512, "h": 512}) + b"trailing-data",
        _gzip_json({"w": 512, "h": 512})[:-3],
        _gzip_json({"w": 512, "h": 512}) + _gzip_json({"w": 1, "h": 1}),
        b"\x1f\x8b",
    ],
    ids=["not-gzip", "trailing-data", "truncated", "concatenated", "magic-only"],
)
def test_validate_tgs_rejects_a_damaged_gzip_stream(data: bytes) -> None:
    assert _rejection(data) == TGS_INVALID_FILE, "a damaged stream must be refused"


@pytest.mark.parametrize(
    "payload",
    [b"{not json", b"\xff\xfe", b"[" * 100_000, b""],
    ids=["broken-json", "not-utf8", "deep-nesting", "empty-json"],
)
def test_validate_tgs_rejects_content_that_is_not_json(payload: bytes) -> None:
    assert _rejection(gzip.compress(payload)) == TGS_INVALID_CONTENT, (
        "content that is not JSON must be refused"
    )


@pytest.mark.parametrize(
    "document",
    [
        {"w": 0, "h": 512},
        {"w": 1025, "h": 512},
        {"w": 512, "h": -1},
        {"w": True, "h": 512},
        {"w": 512.0, "h": 512},
        {"w": "512", "h": 512},
        {"w": 512},
        {"w": 2**63, "h": 2**63},
        [512, 512],
        None,
    ],
    ids=[
        "zero",
        "too-wide",
        "negative",
        "bool",
        "float",
        "string",
        "missing-height",
        "huge",
        "list",
        "null",
    ],
)
def test_validate_tgs_rejects_an_invalid_canvas(document: object) -> None:
    assert _rejection(_gzip_json(document)) == TGS_INVALID_SIZE, (
        "an invalid canvas must be refused"
    )


def test_extract_tgs_validates_before_importing_rlottie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imports: list[str] = []
    monkeypatch.setattr(tgs.importlib, "import_module", _fake_rlottie(imports))
    _extraction_error(gzip.compress(b"0" * (tgs.MAX_TGS_JSON + 1)))
    expected_empty: list[str] = []
    assert imports == expected_empty, "a bomb must never reach the native decoder"


def test_extract_tgs_imports_rlottie_for_a_valid_animation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imports: list[str] = []
    monkeypatch.setattr(tgs.importlib, "import_module", _fake_rlottie(imports))
    tgs.extract_tgs(_gzip_json({"w": 64, "h": 48}))
    expected = ["rlottie_python"]
    assert imports == expected, "a valid sticker must load the decoder once"


def test_extract_tgs_returns_jpeg_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    imports: list[str] = []
    monkeypatch.setattr(tgs.importlib, "import_module", _fake_rlottie(imports))
    frames = tgs.extract_tgs(_gzip_json({"w": 300, "h": 200}))
    formats = []
    for frame in frames:
        with Image.open(io.BytesIO(frame)) as image:
            formats.append(image.format)
    expected = ["JPEG"]
    assert formats == expected, "every frame must be a JPEG"
