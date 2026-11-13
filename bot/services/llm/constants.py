# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Константы для расчёта доступного контекста LLM."""

CONTEXT_SAFETY_MARGIN = 512
# При оценочном подсчёте токенов дополнительно резервируем 15% контекста.
ESTIMATE_CONTEXT_SAFETY_FACTOR = 0.15
# Оценочный резерв контекста на каждую image_url-часть.
IMAGE_TOKEN_RESERVE = 2048
