# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the creation of the protected .env file."""

from pathlib import Path

import pytest

from bot_obormot import initial_env

VALID_TOKEN = "123456789:" + "A" * 35


def test_new_file_is_created_with_private_permissions(tmp_path: Path) -> None:
    home = tmp_path / "home"

    env_path = initial_env.write_initial_env(home)

    assert env_path == home / ".env"
    expected_number = 0o600
    assert env_path.stat().st_mode & 0o777 == expected_number
    expected_number = 0o700
    assert home.stat().st_mode & 0o777 == expected_number
    assert [path.name for path in home.iterdir()] == [".env"]


def test_existing_file_is_refused_and_kept(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        initial_env.write_initial_env(tmp_path)

    expected_text = "SECRET=1\n"
    assert (tmp_path / ".env").read_text(encoding="utf-8") == expected_text
    assert [path.name for path in tmp_path.iterdir()] == [".env"]


def test_force_overwrites_the_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")

    env_path = initial_env.write_initial_env(tmp_path, force=True)

    new_content = "SECRET=1"
    assert new_content not in env_path.read_text(encoding="utf-8")
    expected_number = 0o600
    assert env_path.stat().st_mode & 0o777 == expected_number


def test_placeholders_are_replaced(tmp_path: Path) -> None:
    env_path = initial_env.write_initial_env(tmp_path, token=VALID_TOKEN, supervisor=42)
    lines = env_path.read_text(encoding="utf-8").splitlines()

    assert f"BOT_TOKEN={VALID_TOKEN}" in lines
    supervisor_line = "SUPERVISOR_ID=42"
    assert supervisor_line in lines
    bot_placeholder = "YOUR_TELEGRAM_BOT_TOKEN"
    assert not any(bot_placeholder in line for line in lines)
    supervisor_placeholder = "REPLACE_WITH"
    assert not any(supervisor_placeholder in line for line in lines)


def test_placeholders_remain_when_values_are_not_given(tmp_path: Path) -> None:
    content = initial_env.write_initial_env(tmp_path).read_text(encoding="utf-8")

    assert initial_env.BOT_PLACEHOLDER_LINE in content
    assert initial_env.SUPERVISOR_PLACEHOLDER in content


def test_invalid_token_and_supervisor_are_rejected(tmp_path: Path) -> None:
    injection_value = "bad\nBOT_TOKEN=x"
    with pytest.raises(ValueError, match="token"):
        initial_env.write_initial_env(tmp_path, token=injection_value)
    with pytest.raises(ValueError, match="supervisor"):
        initial_env.write_initial_env(tmp_path, supervisor=0)

    assert not (tmp_path / ".env").exists()


def test_packaged_template_matches_the_repository_example() -> None:
    example = Path(__file__).resolve().parents[2] / ".env.example"

    assert initial_env.load_env_template() == example.read_text(encoding="utf-8")
