import math
import os
import warnings


def get_int(name: str, default: str, minimum: int = 1) -> int:
    value = os.getenv(name, default)

    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"Настройка {name} должна быть целым числом. Получено: {value!r}"
        )

    if result < minimum:
        raise ValueError(
            f"Настройка {name} должна быть не меньше {minimum}. Получено: {result}"
        )

    return result


def get_float(
    name: str,
    default: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = os.getenv(name, default)

    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Настройка {name} должна быть числом. Получено: {value!r}")

    if not math.isfinite(result):
        raise ValueError(
            f"Настройка {name} должна быть конечным числом. Получено: {value!r}"
        )

    if minimum is not None and result < minimum:
        raise ValueError(
            f"Настройка {name} должна быть не меньше {minimum}. Получено: {result}"
        )

    if maximum is not None and result > maximum:
        raise ValueError(
            f"Настройка {name} должна быть не больше {maximum}. Получено: {result}"
        )

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
    value = os.getenv(name, "").strip()

    if not value:
        return set()

    result = set()

    for item in value.split(","):
        item = item.strip()

        if not item:
            continue

        try:
            user_id = int(item)
        except ValueError:
            raise ValueError(f"Настройка {name} содержит некорректный ID: {item!r}")

        if user_id <= 0:
            raise ValueError(
                f"ID в настройке {name} должен быть положительным: {user_id}"
            )

        result.add(user_id)

    return result
