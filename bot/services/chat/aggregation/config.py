# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Пороги и интервалы сборки последовательных сообщений."""

# Порог длины первой части, после которого запускаем сборщик.
MESSAGE_LENGTH_THRESHOLD = 3000

# Максимальное время ожидания следующей части.
MESSAGE_AGGREGATION_WINDOW = 3.0
