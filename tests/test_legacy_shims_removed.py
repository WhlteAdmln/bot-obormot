from pathlib import Path


def test_legacy_service_shim_modules_are_removed():
    project_root = Path(__file__).resolve().parents[1]
    obsolete_modules = (
        "bot/services/animation.py",
        "bot/services/chat_actions.py",
        "bot/services/chat_logging.py",
        "bot/services/chat_processing.py",
        "bot/services/error_handler.py",
        "bot/services/errors.py",
        "bot/services/chat_error_handler.py",
        "bot/services/message_aggregator.py",
        "bot/services/message_formatter.py",
        "bot/services/message_preparation.py",
        "bot/services/user_locks.py",
    )

    assert all(not (project_root / path).exists() for path in obsolete_modules)
