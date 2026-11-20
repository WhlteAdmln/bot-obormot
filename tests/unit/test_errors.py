# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the application error hierarchy and its user texts."""

import pytest

import bot_obormot.errors as errors_package
from bot_obormot.errors import (
    AppError,
    AudiodocAPIError,
    AudiodocEmptyAudioError,
    AudiodocError,
    AudiodocTimeoutError,
    AudiodocUnavailableError,
    BotServiceError,
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
    WhisperAPIError,
    WhisperEmptyAudioError,
    WhisperError,
    WhisperTimeoutError,
    WhisperUnavailableError,
)
from bot_obormot.services.chat.errors import catalog, texts
from bot_obormot.services.chat.errors import handler as chat_error_handler


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


# One instance per class and the exact text the user must see for it.
_EXPECTED_TEXTS: dict[type[AppError], tuple[AppError, str]] = {
    AppError: (AppError("x"), texts.UNEXPECTED_ERROR),
    ValidationError: (ValidationError("x"), texts.UNEXPECTED_ERROR),
    InputTooLongError: (InputTooLongError("x"), texts.input_too_long(Exception())),
    DatabaseError: (DatabaseError("x"), texts.DATABASE_ERROR),
    MediaError: (MediaError("bad media"), "⚠️ bad media"),
    DocumentError: (DocumentError("x"), texts.UNEXPECTED_ERROR),
    DocumentUnavailableError: (
        DocumentUnavailableError("x"),
        texts.DOCUMENT_UNAVAILABLE,
    ),
    DocumentTimeoutError: (DocumentTimeoutError("x"), texts.DOCUMENT_TIMEOUT),
    DocumentAPIError: (DocumentAPIError(500, "x"), texts.DOCUMENT_API),
    DocumentTooLongError: (
        DocumentTooLongError("x"),
        texts.document_too_long(Exception()),
    ),
    LLMError: (LLMError("x"), texts.UNEXPECTED_ERROR),
    LLMUnavailableError: (LLMUnavailableError("x"), texts.LLM_UNAVAILABLE),
    LLMTimeoutError: (LLMTimeoutError("x"), texts.LLM_TIMEOUT),
    LLMAPIError: (LLMAPIError(500, "x"), texts.LLM_API),
    LLMEmptyResponseError: (LLMEmptyResponseError(), texts.LLM_EMPTY_RESPONSE),
    TelegramError: (TelegramError("x"), texts.TELEGRAM_ERROR),
    TelegramFileTooBigError: (
        TelegramFileTooBigError("x"),
        texts.TELEGRAM_FILE_TOO_BIG,
    ),
    AudiodocError: (AudiodocError("x"), texts.WHISPER_ERROR),
    AudiodocEmptyAudioError: (AudiodocEmptyAudioError("x"), texts.WHISPER_EMPTY_AUDIO),
    AudiodocUnavailableError: (
        AudiodocUnavailableError("x"),
        texts.WHISPER_UNAVAILABLE,
    ),
    AudiodocTimeoutError: (AudiodocTimeoutError("x"), texts.WHISPER_TIMEOUT),
    AudiodocAPIError: (AudiodocAPIError("x"), texts.WHISPER_API),
}

_GENERIC_CODES = {"app_error", "validation_error", "document_error", "llm_error"}


def test_every_error_class_has_its_own_unique_code() -> None:
    """Every error class declares a code of its own and no two share one."""
    classes = _app_error_classes()
    codes = [cls.code for cls in classes]

    assert len(set(codes)) == len(codes)
    for cls in classes:
        assert "code" in vars(cls), f"{cls.__name__} must declare its own code"
        assert cls.code == cls.code.lower()
        assert cls.code.replace("_", "").isalnum()


def test_every_error_class_has_a_safe_english_public_message() -> None:
    """Public messages are non-empty English text without internal detail."""
    for cls in _app_error_classes():
        assert "public_message" in vars(cls), f"{cls.__name__} lacks public_message"
        assert cls.public_message.strip()
        assert cls.public_message.isascii()
        assert "http" not in cls.public_message.lower()


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

    class UnmappedError(AppError):
        code = "not_in_the_table"

    assert texts.user_text(ValueError("x")) == texts.UNEXPECTED_ERROR
    assert texts.user_text(UnmappedError("x")) == texts.UNEXPECTED_ERROR


def test_subclass_without_own_code_uses_the_text_of_its_parent() -> None:
    """A subclass that declares no code inherits the text of its base class."""

    class CustomTimeoutError(LLMTimeoutError):
        pass

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


def test_deprecated_names_are_aliases_of_the_new_classes() -> None:
    """Old class names stay importable for one release and are the same objects."""
    assert BotServiceError is AppError
    assert WhisperError is AudiodocError
    assert WhisperEmptyAudioError is AudiodocEmptyAudioError
    assert WhisperUnavailableError is AudiodocUnavailableError
    assert WhisperTimeoutError is AudiodocTimeoutError
    assert WhisperAPIError is AudiodocAPIError
    for name in (
        "BotServiceError",
        "WhisperError",
        "WhisperEmptyAudioError",
        "WhisperUnavailableError",
        "WhisperTimeoutError",
        "WhisperAPIError",
    ):
        assert name in errors_package.__all__


def test_api_errors_keep_status_and_detail() -> None:
    """HTTP status and detail stay available for logging."""
    document_error = DocumentAPIError(502, "bad gateway")
    llm_error = LLMAPIError(503, "busy")

    assert (document_error.status, document_error.detail) == (502, "bad gateway")
    assert str(document_error) == "Document Engine HTTP 502: bad gateway"
    assert (llm_error.status, llm_error.detail) == (503, "busy")
    assert str(llm_error) == "LLM API HTTP 503: busy"


def test_empty_response_text_tells_a_cut_generation_from_a_plain_empty_one() -> None:
    """A response cut by max_tokens gets its own text for the user."""
    cut = LLMEmptyResponseError("length")

    assert texts.user_text(cut) == texts.LLM_TOKEN_LIMIT
    assert texts.user_text(LLMEmptyResponseError("stop")) == texts.LLM_EMPTY_RESPONSE
    assert "length" in str(cut)
