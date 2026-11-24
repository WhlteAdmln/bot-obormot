# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for chat incoming log."""

import logging
from types import SimpleNamespace

import pytest

from bot_obormot.services.chat import incoming_log


def test_incoming_log_records_message_types(caplog: pytest.LogCaptureFixture) -> None:
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

    message_type_line = "INCOMING MESSAGE: type=document"
    assert message_type_line in caplog.text
    document_line = "DOCUMENT INFO: filename=doc.pdf"
    assert document_line in caplog.text
    animation_line = "ANIMATION INFO: mime_type=image/gif"
    assert animation_line in caplog.text


def test_incoming_log_sanitizes_user_supplied_document_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
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

    escaped_filename = r"filename=report.pdf\nERROR forged entry"
    assert escaped_filename in caplog.text
    escaped_mime_type = r"mime_type=application/pdf\rINFO forged entry"
    assert escaped_mime_type in caplog.text
    forged_error_line = "\nERROR forged entry"
    assert forged_error_line not in caplog.text
    forged_info_line = "\rINFO forged entry"
    assert forged_info_line not in caplog.text
