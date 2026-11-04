import logging

from bot.utils.log_filters import SecretsFilter


def test_token_is_redacted_from_log_message():
    token = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789"
    log_filter = SecretsFilter([token])
    record = logging.LogRecord(
        "t",
        logging.ERROR,
        "f",
        1,
        f"url=https://api.telegram.org/file/bot{token}/x",
        (),
        None,
    )

    assert log_filter.filter(record) is True
    assert token not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def test_configured_secrets_are_redacted_from_formatted_arguments():
    secrets_filter = SecretsFilter(["llm-secret-value", "", "short"])
    record = logging.LogRecord(
        "t",
        logging.ERROR,
        "f",
        1,
        "Request failed: %s",
        ("llm-secret-value",),
        None,
    )

    secrets_filter.filter(record)

    assert "llm-secret-value" not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def test_token_is_redacted_from_exception_traceback():
    token = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789"
    secrets_filter = SecretsFilter([token])

    try:
        raise RuntimeError(
            f"download failed: https://api.telegram.org/bot{token}/getFile"
        )
    except RuntimeError:
        record = logging.LogRecord(
            "t",
            logging.ERROR,
            "f",
            1,
            "Telegram request failed",
            (),
            __import__("sys").exc_info(),
        )

    secrets_filter.filter(record)

    assert record.exc_text is not None
    assert token not in record.exc_text
    assert "[REDACTED]" in record.exc_text


def test_logging_setup_attaches_filter_to_root_handlers(monkeypatch):
    from bot.app import logging_setup

    handler = logging.StreamHandler()
    root_logger = logging.getLogger()
    monkeypatch.setattr(root_logger, "handlers", [handler])
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: None)

    logging_setup.configure_logging()

    assert any(isinstance(item, SecretsFilter) for item in handler.filters)
