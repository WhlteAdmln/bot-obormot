# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the creation of the protected .env file."""

from pathlib import Path

import pytest

from bot_obormot import initial_env

VALID_TOKEN = "123456789:" + "A" * 35


def test_new_file_is_created_with_private_permissions(tmp_path: Path) -> None:
    """A new .env has mode 600 and the home directory is private."""
    home = tmp_path / "home"

    env_path = initial_env.write_initial_env(home)

    assert env_path == home / ".env"
    assert env_path.stat().st_mode & 0o777 == 0o600
    assert home.stat().st_mode & 0o777 == 0o700
    assert [path.name for path in home.iterdir()] == [".env"]


def test_existing_file_is_refused_and_kept(tmp_path: Path) -> None:
    """An existing .env is never overwritten without ``force``."""
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        initial_env.write_initial_env(tmp_path)

    assert (tmp_path / ".env").read_text(encoding="utf-8") == "SECRET=1\n"
    assert [path.name for path in tmp_path.iterdir()] == [".env"]


def test_force_overwrites_the_file(tmp_path: Path) -> None:
    """``force`` replaces the file and keeps mode 600."""
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")

    env_path = initial_env.write_initial_env(tmp_path, force=True)

    assert "SECRET=1" not in env_path.read_text(encoding="utf-8")
    assert env_path.stat().st_mode & 0o777 == 0o600


def test_placeholders_are_replaced(tmp_path: Path) -> None:
    """The token and supervisor placeholders are filled in."""
    env_path = initial_env.write_initial_env(tmp_path, token=VALID_TOKEN, supervisor=42)
    lines = env_path.read_text(encoding="utf-8").splitlines()

    assert f"BOT_TOKEN={VALID_TOKEN}" in lines
    assert "SUPERVISOR_ID=42" in lines
    assert not any("YOUR_TELEGRAM_BOT_TOKEN" in line for line in lines)
    assert not any("REPLACE_WITH" in line for line in lines)


def test_placeholders_remain_when_values_are_not_given(tmp_path: Path) -> None:
    """Without options the template placeholders stay for the user to edit."""
    content = initial_env.write_initial_env(tmp_path).read_text(encoding="utf-8")

    assert initial_env.BOT_PLACEHOLDER_LINE in content
    assert initial_env.SUPERVISOR_PLACEHOLDER in content


def test_invalid_token_and_supervisor_are_rejected(tmp_path: Path) -> None:
    """Invalid values never reach the file."""
    injection_value = "bad\nBOT_TOKEN=x"
    with pytest.raises(ValueError, match="token"):
        initial_env.write_initial_env(tmp_path, token=injection_value)
    with pytest.raises(ValueError, match="supervisor"):
        initial_env.write_initial_env(tmp_path, supervisor=0)

    assert not (tmp_path / ".env").exists()


def test_packaged_template_matches_the_repository_example() -> None:
    """The template inside the package is a copy of ``.env.example``."""
    example = Path(__file__).resolve().parents[2] / ".env.example"

    assert initial_env.load_env_template() == example.read_text(encoding="utf-8")
