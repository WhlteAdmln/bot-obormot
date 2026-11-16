# VENDORED: keep identical in bot-obormot and audiodoc. Source of truth: audiodoc.
# Copyright (c) 2026 Nikolai Zelensky
"""Redact configured API secrets and token-like strings from log records."""

import logging
import re

_TOKEN_PATTERN = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")
_BEARER_PATTERN = re.compile(r"(?i)(\b(?:authorization\s*[:=]\s*)?bearer\s+)[^\s,;]+")
_MIN_SECRET_LENGTH = 8


class SecretsFilter(logging.Filter):
    """Replace known secrets, Telegram tokens, and logged Bearer values."""

    def __init__(self, secrets: list[str] | tuple[str, ...]) -> None:
        """Initialize the filter with secrets to redact.

        Args:
            secrets: Values that should be removed from log output.
        """
        super().__init__()
        self._secrets = [
            secret for secret in secrets if secret and len(secret) >= _MIN_SECRET_LENGTH
        ]

    def _clean(self, text: str) -> str:
        cleaned = _TOKEN_PATTERN.sub("[REDACTED]", text)
        cleaned = _BEARER_PATTERN.sub(r"\1[REDACTED]", cleaned)
        for secret in self._secrets:
            cleaned = cleaned.replace(secret, "[REDACTED]")
        return cleaned

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact configured secrets from the rendered message and traceback."""
        message = record.getMessage()
        cleaned = self._clean(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()

        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = self._clean(record.exc_text)
        return True
