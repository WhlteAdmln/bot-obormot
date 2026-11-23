# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the application error hierarchy and its user texts."""

from typing import NamedTuple

import pytest

from bot_obormot.errors import (
    AppError,
    AudiodocAPIError,
    AudiodocEmptyAudioError,
    AudiodocError,
    AudiodocTimeoutError,
    AudiodocUnavailableError,
    DatabaseError,
    DocumentAPIError,
    DocumentError,
    DocumentTimeoutError,
    DocumentTooLongError,
    DocumentUnavailableError,
    InputTooLongError,
    LLMAPIError,
    LLMEmptyResponseError,
    LLMError,
    LLMTimeoutError,
    LLMUnavailableError,
    MediaError,
    TelegramError,
    TelegramFileTooBigError,
    ValidationError,
)
from bot_obormot.services.chat.errors import catalog, texts
from bot_obormot.services.chat.errors import handler as chat_error_handler
from tests.support.errors import CustomTimeoutError, UnmappedError


def _app_error_classes() -> list[type[AppError]]:
    """Returns every error class declared in the ``bot_obormot.errors`` package."""
    found: list[type[AppError]] = [AppError]
    queue: list[type[AppError]] = [AppError]
    while queue:
        current = queue.pop()
        for subclass in current.__subclasses__():
            if (
                subclass.__module__.startswith("bot_obormot.errors")
                and subclass not in found
            ):
                found.append(subclass)
                queue.append(subclass)
    return found


class _Expected(NamedTuple):
    error: AppError
    text: str


_EXPECTED_TEXTS: dict[type[AppError], _Expected] = {
    AppError: _Expected(AppError("x"), texts.UNEXPECTED_ERROR),
    ValidationError: _Expected(ValidationError("x"), texts.UNEXPECTED_ERROR),
    InputTooLongError: _Expected(
        InputTooLongError("x"), texts.input_too_long(Exception())
    ),
    DatabaseError: _Expected(DatabaseError("x"), texts.DATABASE_ERROR),
    MediaError: _Expected(MediaError("bad media"), "⚠️ bad media"),
    DocumentError: _Expected(DocumentError("x"), texts.UNEXPECTED_ERROR),
    DocumentUnavailableError: _Expected(
        DocumentUnavailableError("x"),
        texts.DOCUMENT_UNAVAILABLE,
    ),
    DocumentTimeoutError: _Expected(DocumentTimeoutError("x"), texts.DOCUMENT_TIMEOUT),
    DocumentAPIError: _Expected(DocumentAPIError(500, "x"), texts.DOCUMENT_API),
    DocumentTooLongError: _Expected(
        DocumentTooLongError("x"),
        texts.document_too_long(Exception()),
    ),
    LLMError: _Expected(LLMError("x"), texts.UNEXPECTED_ERROR),
    LLMUnavailableError: _Expected(LLMUnavailableError("x"), texts.LLM_UNAVAILABLE),
    LLMTimeoutError: _Expected(LLMTimeoutError("x"), texts.LLM_TIMEOUT),
    LLMAPIError: _Expected(LLMAPIError(500, "x"), texts.LLM_API),
    LLMEmptyResponseError: _Expected(LLMEmptyResponseError(), texts.LLM_EMPTY_RESPONSE),
    TelegramError: _Expected(TelegramError("x"), texts.TELEGRAM_ERROR),
    TelegramFileTooBigError: _Expected(
        TelegramFileTooBigError("x"),
        texts.TELEGRAM_FILE_TOO_BIG,
    ),
    AudiodocError: _Expected(AudiodocError("x"), texts.WHISPER_ERROR),
    AudiodocEmptyAudioError: _Expected(
        AudiodocEmptyAudioError("x"), texts.WHISPER_EMPTY_AUDIO
    ),
    AudiodocUnavailableError: _Expected(
        AudiodocUnavailableError("x"),
        texts.WHISPER_UNAVAILABLE,
    ),
    AudiodocTimeoutError: _Expected(AudiodocTimeoutError("x"), texts.WHISPER_TIMEOUT),
    AudiodocAPIError: _Expected(AudiodocAPIError("x"), texts.WHISPER_API),
}

_GENERIC_CODES = {"app_error", "validation_error", "document_error", "llm_error"}


def test_every_error_class_has_its_own_unique_code() -> None:
    """Every error class declares a code of its own and no two share one."""
    classes = _app_error_classes()
    codes = [cls.code for cls in classes]

    assert len(set(codes)) == len(codes)
    for cls in classes:
        expected_fragment = "code"
        assert expected_fragment in vars(cls), (
            f"{cls.__name__} must declare its own code"
        )
        assert cls.code == cls.code.lower()
        assert cls.code.replace("_", "").isalnum()


def test_every_error_class_has_a_safe_english_public_message() -> None:
    """Public messages are non-empty English text without internal detail."""
    for cls in _app_error_classes():
        expected_fragment = "public_message"
        assert expected_fragment in vars(cls), f"{cls.__name__} lacks public_message"
        assert cls.public_message.strip()
        assert cls.public_message.isascii()
        expected_fragment = "http"
        assert expected_fragment not in cls.public_message.lower()


def test_every_code_has_a_user_text_and_no_text_is_orphaned() -> None:
    """The texts table maps exactly the codes that the error classes declare."""
    declared = {cls.code for cls in _app_error_classes()}

    assert set(texts.USER_TEXTS) == declared


def test_expected_texts_table_covers_every_error_class() -> None:
    """A new error class must be added to the expected texts of this module."""
    assert set(_EXPECTED_TEXTS) == set(_app_error_classes())


@pytest.mark.parametrize(
    ("error", "expected"),
    list(_EXPECTED_TEXTS.values()),
    ids=[cls.code for cls in _EXPECTED_TEXTS],
)
def test_user_text_is_chosen_by_error_code(error: AppError, expected: str) -> None:
    """Each code is turned into its Russian user text by ``texts.user_text``."""
    assert texts.user_text(error) == expected


def test_only_generic_codes_use_the_unexpected_error_text() -> None:
    """Every specific code has its own text; only base codes are generic."""
    generic = {
        error.code
        for error, expected in _EXPECTED_TEXTS.values()
        if expected == texts.UNEXPECTED_ERROR
    }

    assert generic == _GENERIC_CODES


def test_user_text_falls_back_for_foreign_and_unmapped_errors() -> None:
    """Errors without a known code get the unexpected-error text."""
    assert texts.user_text(ValueError("x")) == texts.UNEXPECTED_ERROR
    assert texts.user_text(UnmappedError("x")) == texts.UNEXPECTED_ERROR


def test_subclass_without_own_code_uses_the_text_of_its_parent() -> None:
    """A subclass that declares no code inherits the text of its base class."""
    assert texts.user_text(CustomTimeoutError("x")) == texts.LLM_TIMEOUT


@pytest.mark.parametrize(
    ("error", "expected"),
    list(_EXPECTED_TEXTS.values()),
    ids=[cls.code for cls in _EXPECTED_TEXTS],
)
@pytest.mark.asyncio
async def test_chat_error_handler_reports_text_for_every_code(
    monkeypatch: pytest.MonkeyPatch, error: AppError, expected: str
) -> None:
    """The chat handler sends the text of the error code to the user."""
    captured: list[str] = []

    async def fake_report(_message: object, _status: object, text: str) -> None:
        captured.append(text)

    monkeypatch.setattr(chat_error_handler, "report_error", fake_report)

    await chat_error_handler.handle_chat_error(object(), None, 1, error)

    assert captured == [expected]


def test_every_catalog_rule_targets_a_class_with_a_user_text() -> None:
    """Catalog rules only describe logging; their types resolve to a text."""
    for rule in catalog.CHAT_ERROR_RULES:
        assert issubclass(rule.error_type, AppError)
        assert rule.error_type.code in texts.USER_TEXTS


def test_api_errors_keep_status_and_detail() -> None:
    """HTTP status and detail stay available for logging."""
    document_error = DocumentAPIError(502, "bad gateway")
    llm_error = LLMAPIError(503, "busy")

    assert (document_error.status, document_error.detail) == (502, "bad gateway")
    expected_text = "Document Engine HTTP 502: bad gateway"
    assert str(document_error) == expected_text
    assert (llm_error.status, llm_error.detail) == (503, "busy")
    expected_text = "LLM API HTTP 503: busy"
    assert str(llm_error) == expected_text


def test_empty_response_text_tells_a_cut_generation_from_a_plain_empty_one() -> None:
    """A response cut by max_tokens gets its own text for the user."""
    cut = LLMEmptyResponseError("length")

    assert texts.user_text(cut) == texts.LLM_LENGTH_LIMIT
    assert texts.user_text(LLMEmptyResponseError("stop")) == texts.LLM_EMPTY_RESPONSE
    expected_fragment = "length"
    assert expected_fragment in str(cut)
