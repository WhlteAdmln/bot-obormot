# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""User-facing status messages for the LLM service."""

HEALTH_AVAILABLE = "Доступен"
HEALTH_API_UNAVAILABLE = "HTTP {status}: LLM API недоступен"
HEALTH_TIMEOUT = "Тайм-аут при обращении к LLM-серверу"
HEALTH_SERVER_UNAVAILABLE = "LLM-сервер недоступен"
HEALTH_CHECK_ERROR = "Ошибка проверки LLM-сервера"
