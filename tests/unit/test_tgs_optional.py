# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the optional animated-sticker decoder."""

import gzip
import json
import logging
import sys

import pytest

from bot_obormot.errors import MediaError
from bot_obormot.services.media.animation import extract_animation_frames, tgs
from bot_obormot.services.media.texts import TGS_SUPPORT_UNAVAILABLE


def _valid_tgs() -> bytes:
    """Build a minimal valid TGS payload."""
    return gzip.compress(json.dumps({"w": 512, "h": 512}).encode("utf-8"))


@pytest.fixture(autouse=True)
def _reset_warning_cache() -> None:
    """Allow every test to observe the one-time warning."""
    tgs._warn_tgs_unavailable.cache_clear()


def test_missing_decoder_gives_a_polite_media_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing optional module is reported with a user-facing message."""
    monkeypatch.setitem(sys.modules, "rlottie_python", None)

    with pytest.raises(MediaError, match=TGS_SUPPORT_UNAVAILABLE):
        tgs.extract_tgs(_valid_tgs())


def test_missing_decoder_warns_only_once(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The log warning about the missing extra is written one time."""
    monkeypatch.setitem(sys.modules, "rlottie_python", None)

    with caplog.at_level(logging.WARNING, logger=tgs.logger.name):
        for _ in range(3):
            with pytest.raises(MediaError):
                tgs.extract_tgs(_valid_tgs())

    warnings = [record for record in caplog.records if "bot-obormot[tgs]" in record.msg]
    assert len(warnings) == 1


def test_invalid_file_is_still_rejected_before_the_import_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation errors keep priority over the missing-extra message."""
    monkeypatch.setitem(sys.modules, "rlottie_python", None)

    with pytest.raises(MediaError) as error:
        tgs.extract_tgs(b"not-a-gzip-file")

    assert str(error.value) != TGS_SUPPORT_UNAVAILABLE


@pytest.mark.asyncio
async def test_animation_pipeline_passes_the_polite_error_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public animation API does not wrap the polite message."""
    monkeypatch.setitem(sys.modules, "rlottie_python", None)

    with pytest.raises(MediaError, match=TGS_SUPPORT_UNAVAILABLE):
        await extract_animation_frames(_valid_tgs(), "tgs")


def test_support_check_follows_the_installed_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The doctor helper reports whether the optional module can be found."""
    monkeypatch.setitem(sys.modules, "rlottie_python", None)
    assert tgs.tgs_support_available() is False
