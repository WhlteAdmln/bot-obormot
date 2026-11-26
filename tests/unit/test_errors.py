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
    AppError: _Expected(AppError("disk quota hit"), texts.UNEXPECTED_ERROR),
    ValidationError: _Expected(
        ValidationError("bad prompt shape"), texts.UNEXPECTED_ERROR
    ),
    InputTooLongError: _Expected(
        InputTooLongError("input of 9001 chars"), texts.input_too_long(Exception())
    ),
    DatabaseError: _Expected(DatabaseError("sqlite locked"), texts.DATABASE_ERROR),
    MediaError: _Expected(MediaError("bad media"), "⚠️ bad media"),
    DocumentError: _Expected(DocumentError("pdf parse broke"), texts.UNEXPECTED_ERROR),
    DocumentUnavailableError: _Expected(
        DocumentUnavailableError("engine down"),
        texts.DOCUMENT_UNAVAILABLE,
    ),
    DocumentTimeoutError: _Expected(
        DocumentTimeoutError("engine slow"), texts.DOCUMENT_TIMEOUT
    ),
    DocumentAPIError: _Expected(
        DocumentAPIError(500, "too many pages"), texts.DOCUMENT_API
    ),
    DocumentTooLongError: _Expected(
        DocumentTooLongError("model mixup"),
        texts.document_too_long(Exception()),
    ),
    LLMError: _Expected(LLMError("llm offline"), texts.UNEXPECTED_ERROR),
    LLMUnavailableError: _Expected(
        LLMUnavailableError("llm slow"), texts.LLM_UNAVAILABLE
    ),
    LLMTimeoutError: _Expected(LLMTimeoutError("tg hiccup"), texts.LLM_TIMEOUT),
    LLMAPIError: _Expected(LLMAPIError(500, "file of 3 GB"), texts.LLM_API),
    LLMEmptyResponseError: _Expected(LLMEmptyResponseError(), texts.LLM_EMPTY_RESPONSE),
    TelegramError: _Expected(TelegramError("asr crashed"), texts.TELEGRAM_ERROR),
    TelegramFileTooBigError: _Expected(
        TelegramFileTooBigError("silent clip"),
        texts.TELEGRAM_FILE_TOO_BIG,
    ),
    AudiodocError: _Expected(AudiodocError("asr offline"), texts.WHISPER_ERROR),
    AudiodocEmptyAudioError: _Expected(
        AudiodocEmptyAudioError("asr slow"), texts.WHISPER_EMPTY_AUDIO
    ),
    AudiodocUnavailableError: _Expected(
        AudiodocUnavailableError("asr 502 body"),
        texts.WHISPER_UNAVAILABLE,
    ),
    AudiodocTimeoutError: _Expected(
        AudiodocTimeoutError("asr gateway lost"), texts.WHISPER_TIMEOUT
    ),
    AudiodocAPIError: _Expected(AudiodocAPIError("asr payload odd"), texts.WHISPER_API),
}

_GENERIC_CODES = {"app_error", "validation_error", "document_error", "llm_error"}


def test_every_error_class_has_its_own_unique_code() -> None:
    codes = [cls.code for cls in _app_error_classes()]

    assert len(set(codes)) == len(codes), "two error classes share a code"


@pytest.mark.parametrize("cls", _app_error_classes(), ids=lambda cls: cls.__name__)
def test_error_class_declares_its_own_code(cls: type[AppError]) -> None:
    code_field = "code"
    assert code_field in vars(cls), f"{cls.__name__} must declare its own code"


@pytest.mark.parametrize("cls", _app_error_classes(), ids=lambda cls: cls.__name__)
def test_error_code_is_lower_case(cls: type[AppError]) -> None:
    assert cls.code == cls.code.lower(), f"{cls.__name__} has an upper-case code"


@pytest.mark.parametrize("cls", _app_error_classes(), ids=lambda cls: cls.__name__)
def test_error_code_has_only_letters_digits_and_underscores(
    cls: type[AppError],
) -> None:
    separator = "_"
    empty = ""
    bare_code = cls.code.replace(separator, empty)
    assert bare_code.isalnum(), f"{cls.__name__} has a code with other characters"


@pytest.mark.parametrize("cls", _app_error_classes(), ids=lambda cls: cls.__name__)
def test_error_class_declares_its_own_public_message(cls: type[AppError]) -> None:
    public_message_field = "public_message"
    assert public_message_field in vars(cls), f"{cls.__name__} lacks public_message"


@pytest.mark.parametrize("cls", _app_error_classes(), ids=lambda cls: cls.__name__)
def test_error_public_message_is_not_blank(cls: type[AppError]) -> None:
    assert cls.public_message.strip(), f"{cls.__name__} has a blank public_message"


@pytest.mark.parametrize("cls", _app_error_classes(), ids=lambda cls: cls.__name__)
def test_error_public_message_is_ascii(cls: type[AppError]) -> None:
    assert cls.public_message.isascii(), f"{cls.__name__} public_message is not ASCII"


@pytest.mark.parametrize("cls", _app_error_classes(), ids=lambda cls: cls.__name__)
def test_error_public_message_does_not_mention_http(cls: type[AppError]) -> None:
    http_field = "http"
    message = cls.public_message.lower()
    assert http_field not in message, f"{cls.__name__} public_message mentions HTTP"


def test_every_code_has_a_user_text_and_no_text_is_orphaned() -> None:
    declared = {cls.code for cls in _app_error_classes()}

    assert set(texts.USER_TEXTS) == declared, "user texts and error codes differ"


def test_expected_texts_table_covers_every_error_class() -> None:
    covered = set(_EXPECTED_TEXTS)
    assert covered == set(_app_error_classes()), "the expected table misses a class"


@pytest.mark.parametrize(
    ("error", "expected"),
    list(_EXPECTED_TEXTS.values()),
    ids=[cls.code for cls in _EXPECTED_TEXTS],
)
def test_user_text_is_chosen_by_error_code(error: AppError, expected: str) -> None:
    assert texts.user_text(error) == expected, f"{error.code} has another user text"


def test_only_generic_codes_use_the_unexpected_error_text() -> None:
    generic = {
        error.code
        for error, expected in _EXPECTED_TEXTS.values()
        if expected == texts.UNEXPECTED_ERROR
    }

    assert generic == _GENERIC_CODES, "another code uses the unexpected error text"


@pytest.mark.parametrize(
    "error",
    [ValueError("plain value slip"), UnmappedError("unmapped glitch 42")],
    ids=["foreign", "unmapped"],
)
def test_user_text_falls_back_for_foreign_and_unmapped_errors(
    error: Exception,
) -> None:
    actual = texts.user_text(error)
    assert actual == texts.UNEXPECTED_ERROR, "the error got a specific user text"


def test_subclass_without_own_code_uses_the_text_of_its_parent() -> None:
    error = CustomTimeoutError("custom wait expired")
    actual = texts.user_text(error)
    assert actual == texts.LLM_TIMEOUT, "the subclass did not inherit the parent text"


@pytest.mark.parametrize(
    ("error", "expected"),
    list(_EXPECTED_TEXTS.values()),
    ids=[cls.code for cls in _EXPECTED_TEXTS],
)
@pytest.mark.asyncio
async def test_chat_error_handler_reports_text_for_every_code(
    monkeypatch: pytest.MonkeyPatch, error: AppError, expected: str
) -> None:
    captured: list[str] = []

    async def fake_report(_message: object, _status: object, text: str) -> None:
        captured.append(text)

    monkeypatch.setattr(chat_error_handler, "report_error", fake_report)

    await chat_error_handler.handle_chat_error(object(), None, 1, error)

    expected_texts = [expected]
    assert captured == expected_texts, f"{error.code} was reported with another text"


@pytest.mark.parametrize(
    "rule",
    catalog.CHAT_ERROR_RULES,
    ids=lambda rule: rule.error_type.__name__,
)
def test_catalog_rule_targets_an_application_error(
    rule: catalog.ChatErrorRule,
) -> None:
    assert issubclass(rule.error_type, AppError), "a rule targets a foreign error"


@pytest.mark.parametrize(
    "rule",
    catalog.CHAT_ERROR_RULES,
    ids=lambda rule: rule.error_type.__name__,
)
def test_catalog_rule_targets_a_class_with_a_user_text(
    rule: catalog.ChatErrorRule,
) -> None:
    code = rule.error_type.code
    assert code in texts.USER_TEXTS, f"the rule for {code} has no user text"


def test_document_api_error_keeps_status_and_detail() -> None:
    status = 502
    detail = "bad gateway"
    error = DocumentAPIError(status, detail)
    expected = (status, detail)
    assert (error.status, error.detail) == expected, "status or detail was lost"


def test_document_api_error_text_names_status_and_detail() -> None:
    error = DocumentAPIError(504, "upstream sleeps")
    expected_text = "Document Engine HTTP 504: upstream sleeps"
    assert str(error) == expected_text, "the document API error text differs"


def test_llm_api_error_keeps_status_and_detail() -> None:
    status = 503
    detail = "busy"
    error = LLMAPIError(status, detail)
    expected = (status, detail)
    assert (error.status, error.detail) == expected, "status or detail was lost"


def test_llm_api_error_text_names_status_and_detail() -> None:
    error = LLMAPIError(429, "slow down please")
    expected_text = "LLM API HTTP 429: slow down please"
    assert str(error) == expected_text, "the LLM API error text differs"


def test_empty_response_cut_by_length_uses_the_length_limit_text() -> None:
    reason = "length"
    actual = texts.user_text(LLMEmptyResponseError(reason))
    assert actual == texts.LLM_LENGTH_LIMIT, "a cut generation got another text"


def test_empty_response_with_stop_uses_the_empty_response_text() -> None:
    reason = "stop"
    actual = texts.user_text(LLMEmptyResponseError(reason))
    assert actual == texts.LLM_EMPTY_RESPONSE, "a plain empty answer got another text"


def test_empty_response_cut_by_length_names_the_reason() -> None:
    reason = "length"
    error = LLMEmptyResponseError(reason)
    assert reason in str(error), "the error text does not name the finish reason"
