# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Фильтры для удаления секретов из записей журнала."""

import logging
import re

_TOKEN_PATTERN = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")
_MIN_SECRET_LENGTH = 8


class SecretsFilter(logging.Filter):
    """Заменяет токены и секреты в записях лога на [REDACTED]."""

    def __init__(self, secrets: list[str]) -> None:
        """Remembers the secrets long enough to be worth redacting."""
        super().__init__()
        self._secrets = [
            secret for secret in secrets if secret and len(secret) >= _MIN_SECRET_LENGTH
        ]

    def _clean(self, text: str) -> str:
        text = _TOKEN_PATTERN.sub("[REDACTED]", text)

        for secret in self._secrets:
            text = text.replace(secret, "[REDACTED]")

        return text

    def filter(self, record: logging.LogRecord) -> bool:
        """Redacts secrets from the record message and traceback text."""
        message = record.getMessage()
        cleaned = self._clean(message)

        if cleaned != message:
            record.msg = cleaned
            record.args = ()

        # Трассировка ошибки тоже может содержать токен.
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)

        if record.exc_text:
            record.exc_text = self._clean(record.exc_text)

        return True
