# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Helpers that read and validate settings from environment variables."""

import math
import os
import warnings


def get_bool(name: str, default: bool = False) -> bool:
    """Читает логическую переменную окружения (true/false, 1/0, yes/no, on/off)."""
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    normalized = value.strip().lower()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    msg = f"Настройка {name} должна быть true или false. Получено: {value!r}"
    raise ValueError(msg)


def get_int(name: str, default: str, minimum: int = 1) -> int:
    """Reads an integer environment variable and checks its lower bound."""
    value = os.getenv(name, default)

    try:
        result = int(value)
    except (TypeError, ValueError) as err:
        msg = f"Настройка {name} должна быть целым числом. Получено: {value!r}"
        raise ValueError(msg) from err

    if result < minimum:
        msg = f"Настройка {name} должна быть не меньше {minimum}. Получено: {result}"
        raise ValueError(msg)

    return result


def get_optional_int(name: str, minimum: int = 1) -> int | None:
    """Читает необязательное целое число; пустое значение означает None."""
    value = os.getenv(name)

    if value is None or not value.strip():
        return None

    try:
        result = int(value)
    except (TypeError, ValueError) as err:
        msg = f"Настройка {name} должна быть целым числом. Получено: {value!r}"
        raise ValueError(msg) from err

    if result < minimum:
        msg = f"Настройка {name} должна быть не меньше {minimum}. Получено: {result}"
        raise ValueError(msg)

    return result


def get_float(
    name: str,
    default: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Reads a finite float environment variable and checks its bounds."""
    value = os.getenv(name, default)

    try:
        result = float(value)
    except (TypeError, ValueError) as err:
        msg = f"Настройка {name} должна быть числом. Получено: {value!r}"
        raise ValueError(msg) from err

    if not math.isfinite(result):
        msg = f"Настройка {name} должна быть конечным числом. Получено: {value!r}"
        raise ValueError(msg)

    if minimum is not None and result < minimum:
        msg = f"Настройка {name} должна быть не меньше {minimum}. Получено: {result}"
        raise ValueError(msg)

    if maximum is not None and result > maximum:
        msg = f"Настройка {name} должна быть не больше {maximum}. Получено: {result}"
        raise ValueError(msg)

    return result


def get_log_level() -> str:
    """Возвращает допустимый уровень логирования."""
    value = os.getenv("LOG_LEVEL", "INFO").strip().upper()

    allowed_levels = {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }

    if value not in allowed_levels:
        warnings.warn(
            f"Некорректный LOG_LEVEL={value!r}. Используется уровень INFO.",
            RuntimeWarning,
            stacklevel=2,
        )
        return "INFO"

    return value


def parse_ids(name: str) -> set[int]:
    """Parses a comma-separated environment variable into positive integer IDs."""
    value = os.getenv(name, "").strip()

    if not value:
        return set()

    result = set()

    for raw_item in value.split(","):
        item = raw_item.strip()

        if not item:
            continue

        try:
            user_id = int(item)
        except ValueError as err:
            msg = f"Настройка {name} содержит некорректный ID: {item!r}"
            raise ValueError(msg) from err

        if user_id <= 0:
            msg = f"ID в настройке {name} должен быть положительным: {user_id}"
            raise ValueError(msg)

        result.add(user_id)

    return result
