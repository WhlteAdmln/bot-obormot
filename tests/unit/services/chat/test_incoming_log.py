# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for chat incoming log."""

import logging
from types import SimpleNamespace

import pytest

from bot_obormot.services.chat import incoming_log


def _message(
    content_type: str,
    document: SimpleNamespace | None = None,
    animation: SimpleNamespace | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        content_type=content_type,
        animation=animation,
        video=None,
        document=document,
        sticker=None,
        photo=None,
    )


def _logged(caplog: pytest.LogCaptureFixture, message: SimpleNamespace) -> list[str]:
    with caplog.at_level(logging.INFO, logger=incoming_log.logger.name):
        incoming_log.log_incoming_message(message)
    return [record.getMessage() for record in caplog.records]


def _document(file_name: object, mime_type: object) -> SimpleNamespace:
    return _message(
        "document", document=SimpleNamespace(file_name=file_name, mime_type=mime_type)
    )


def test_logs_the_message_type_and_flags(caplog: pytest.LogCaptureFixture) -> None:
    animation = SimpleNamespace(mime_type="video/mp4", file_id="CgACAgIAAx")
    lines = _logged(caplog, _message("animation", animation=animation))
    expected = (
        "INCOMING MESSAGE: type=animation, animation=True, video=False, "
        "document=False, sticker=False, photo=False"
    )
    assert lines[0] == expected, "the summary line is wrong"


def test_logs_the_animation_details(caplog: pytest.LogCaptureFixture) -> None:
    animation = SimpleNamespace(mime_type="image/gif", file_id="gif-id-77")
    lines = _logged(caplog, _message("animation", animation=animation))
    expected = "ANIMATION INFO: mime_type=image/gif, file_id=gif-id-77"
    assert lines[1] == expected, "the animation line is wrong"


def test_logs_only_the_summary_for_plain_text(caplog: pytest.LogCaptureFixture) -> None:
    lines = _logged(caplog, _message("text"))
    assert len(lines) == 1, "plain text must produce one line"


@pytest.mark.parametrize(
    ("file_name", "mime_type", "expected"),
    [
        (
            "doc.pdf",
            "application/pdf",
            "DOCUMENT INFO: filename=doc.pdf, mime_type=application/pdf",
        ),
        (
            "report.pdf\nERROR forged entry",
            "application/pdf\rINFO forged entry",
            (
                "DOCUMENT INFO: filename=report.pdf\\nERROR forged entry, "
                "mime_type=application/pdf\\rINFO forged entry"
            ),
        ),
        (
            "\x1b[2Jcleared.txt",
            "text/plain",
            "DOCUMENT INFO: filename=?[2Jcleared.txt, mime_type=text/plain",
        ),
        (
            "invoice\u202efdp.exe",
            "application/x-msdownload",
            (
                "DOCUMENT INFO: filename=invoice?fdp.exe, "
                "mime_type=application/x-msdownload"
            ),
        ),
        (
            "line\u2028split.doc",
            None,
            "DOCUMENT INFO: filename=line?split.doc, mime_type=",
        ),
        (
            None,
            None,
            "DOCUMENT INFO: filename=, mime_type=",
        ),
        (
            "w" * 500,
            "application/zip",
            f"DOCUMENT INFO: filename={'w' * 120}, mime_type=application/zip",
        ),
    ],
    ids=[
        "plain",
        "forged-lines",
        "ansi-escape",
        "bidi-override",
        "line-separator",
        "missing",
        "overlong",
    ],
)
def test_logs_document_metadata_as_one_safe_line(
    caplog: pytest.LogCaptureFixture,
    file_name: object,
    mime_type: object,
    expected: str,
) -> None:
    lines = _logged(caplog, _document(file_name, mime_type))
    assert lines[1] == expected, "the document line is not safe"
