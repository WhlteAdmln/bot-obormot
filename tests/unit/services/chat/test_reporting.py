# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for chat reporting."""

import logging

import pytest

from bot_obormot.services.chat import reporting
from tests.support.chat_streaming import FakeReplyMessage


@pytest.mark.asyncio
async def test_reporting_answers_when_no_status_and_logs_send_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    message = FakeReplyMessage(failures=[RuntimeError("telegram unavailable")])
    with caplog.at_level(logging.ERROR, logger=reporting.logger.name):
        await reporting.report_error(message, None, "ошибка")

    send_warning = "Could not send error message"
    assert send_warning in caplog.text


@pytest.mark.asyncio
async def test_reporting_uses_safe_edit_when_status_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = []

    async def fake_safe_edit(message: object, text: str) -> None:
        captured.append((message, text))

    monkeypatch.setattr(reporting, "safe_edit", fake_safe_edit)
    message = object()
    status = object()

    await reporting.report_error(message, status, "ошибка")
    assert captured == [(status, "ошибка")]
