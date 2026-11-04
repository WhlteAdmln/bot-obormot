import pytest

from bot.config.env import get_bool


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        (" YES ", True),
        ("on", True),
        ("0", False),
        ("false", False),
        (" NO ", False),
        ("off", False),
    ],
)
def test_get_bool_parses_supported_values(monkeypatch, value, expected):
    monkeypatch.setenv("TEST_BOOL_SETTING", value)

    assert get_bool("TEST_BOOL_SETTING") is expected


def test_get_bool_uses_default_for_missing_or_empty_value(monkeypatch):
    monkeypatch.delenv("TEST_BOOL_SETTING", raising=False)
    assert get_bool("TEST_BOOL_SETTING") is False
    assert get_bool("TEST_BOOL_SETTING", True) is True

    monkeypatch.setenv("TEST_BOOL_SETTING", "   ")
    assert get_bool("TEST_BOOL_SETTING", True) is True


def test_get_bool_rejects_invalid_value(monkeypatch):
    monkeypatch.setenv("TEST_BOOL_SETTING", "sometimes")

    with pytest.raises(ValueError, match="TEST_BOOL_SETTING"):
        get_bool("TEST_BOOL_SETTING")


def test_config_loads_env_from_project_root_only(monkeypatch):
    import importlib

    import dotenv
    import bot.config as config_module
    from bot.config.paths import PROJECT_ROOT

    loaded_paths = []
    original_load_dotenv = dotenv.load_dotenv
    monkeypatch.setattr(
        dotenv,
        "load_dotenv",
        lambda dotenv_path: loaded_paths.append(dotenv_path),
    )

    importlib.reload(config_module)

    assert loaded_paths == [PROJECT_ROOT / ".env"]
    # Keep the reloaded package free of the test spy after monkeypatch teardown.
    config_module.load_dotenv = original_load_dotenv
