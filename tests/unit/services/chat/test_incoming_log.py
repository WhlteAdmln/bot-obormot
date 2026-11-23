# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for chat incoming log."""

import logging
from types import SimpleNamespace

import pytest

from bot_obormot.services.chat import incoming_log


def test_incoming_log_records_message_types(caplog: pytest.LogCaptureFixture) -> None:
    """Incoming log records message types."""
    document = SimpleNamespace(file_name="doc.pdf", mime_type="application/pdf")
    animation = SimpleNamespace(mime_type="image/gif", file_id="gif-id")
    message = SimpleNamespace(
        content_type="document",
        animation=animation,
        video=None,
        document=document,
        sticker=None,
        photo=None,
    )

    with caplog.at_level(logging.INFO, logger=incoming_log.logger.name):
        incoming_log.log_incoming_message(message)

    expected_fragment = "INCOMING MESSAGE: type=document"
    assert expected_fragment in caplog.text
    expected_fragment = "DOCUMENT INFO: filename=doc.pdf"
    assert expected_fragment in caplog.text
    expected_fragment = "ANIMATION INFO: mime_type=image/gif"
    assert expected_fragment in caplog.text


def test_incoming_log_sanitizes_user_supplied_document_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Incoming log sanitizes user supplied document metadata."""
    document = SimpleNamespace(
        file_name="report.pdf\nERROR forged entry",
        mime_type="application/pdf\rINFO forged entry",
    )
    message = SimpleNamespace(
        content_type="document",
        animation=None,
        video=None,
        document=document,
        sticker=None,
        photo=None,
    )

    with caplog.at_level(logging.INFO, logger=incoming_log.logger.name):
        incoming_log.log_incoming_message(message)

    expected_fragment = r"filename=report.pdf\nERROR forged entry"
    assert expected_fragment in caplog.text
    expected_fragment = r"mime_type=application/pdf\rINFO forged entry"
    assert expected_fragment in caplog.text
    expected_fragment = "\nERROR forged entry"
    assert expected_fragment not in caplog.text
    expected_fragment = "\rINFO forged entry"
    assert expected_fragment not in caplog.text
