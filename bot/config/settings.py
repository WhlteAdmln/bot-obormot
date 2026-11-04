import os

from bot.config.env import get_bool, get_float, get_int, get_log_level, parse_ids
from bot.config.prompts import load_default_system_prompt


class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

    LOG_LEVEL = get_log_level()

    # Supervisor — единственный главный администратор.
    SUPERVISOR_ID = get_int("SUPERVISOR_ID", "")

    # Используется для первоначального переноса администраторов в SQLite.
    ADMIN_IDS = parse_ids("ADMIN_IDS")

    ALLOWED_USERS = parse_ids("ALLOWED_USERS")

    # Если True, бот открыт всем. По умолчанию доступ закрыт.
    ALLOW_ALL_USERS = get_bool("ALLOW_ALL_USERS", False)

    LLM_BASE_URL = os.getenv(
        "LLM_BASE_URL",
        "http://127.0.0.1:8080/v1",
    ).rstrip("/")

    LLM_API_KEY = os.getenv("LLM_API_KEY", "not-needed")
    LLM_MODEL = os.getenv("LLM_MODEL", "local-model")

    LLM_TEMPERATURE = get_float(
        "LLM_TEMPERATURE",
        "0.7",
        minimum=0.0,
    )

    LLM_TOP_P = get_float(
        "LLM_TOP_P",
        "0.9",
        minimum=0.0,
        maximum=1.0,
    )

    LLM_MAX_TOKENS = get_int("LLM_MAX_TOKENS", "2048")
    LLM_TIMEOUT = get_int("LLM_TIMEOUT", "300")

    LLM_MAX_CONCURRENT_GENERATIONS = get_int(
        "LLM_MAX_CONCURRENT_GENERATIONS",
        "1",
    )

    # Лимит истории в полных обменах user + assistant.
    DEFAULT_HISTORY_EXCHANGES = 30
    MAX_HISTORY_EXCHANGES = get_int(
        "MAX_HISTORY_EXCHANGES",
        "1000",
    )

    # Максимальное число хранимых полных обменов на пользователя.
    MAX_STORED_EXCHANGES = get_int("MAX_STORED_EXCHANGES", "2000")

    STREAM_UPDATE_INTERVAL = get_float(
        "STREAM_UPDATE_INTERVAL",
        "1.0",
        minimum=0.0,
    )

    if STREAM_UPDATE_INTERVAL == 0:
        raise ValueError("STREAM_UPDATE_INTERVAL должен быть больше нуля")

    DATABASE_PATH = os.getenv("DATABASE_PATH", "data/bot.db").strip()

    if not DATABASE_PATH:
        raise ValueError("DATABASE_PATH не может быть пустым")

    DEFAULT_SYSTEM_PROMPT = load_default_system_prompt()

    WHISPER_API_URL = os.getenv(
        "WHISPER_API_URL",
        "",
    ).rstrip("/")
    WHISPER_API_KEY = os.getenv("WHISPER_API_KEY", "").strip()

    WHISPER_TIMEOUT = get_int(
        "WHISPER_TIMEOUT",
        "180",
    )

    DOCUMENT_API_URL = (
        os.getenv(
            "DOCUMENT_API_URL",
            "",
        )
        .strip()
        .rstrip("/")
    )
    DOCUMENT_API_KEY = os.getenv("DOCUMENT_API_KEY", "").strip()

    DOCUMENT_TIMEOUT = get_int(
        "DOCUMENT_TIMEOUT",
        "300",
    )


config = Config()
