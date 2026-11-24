# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the creation of the protected .env file."""

import contextlib
from pathlib import Path

import pytest

from bot_obormot import initial_env


def _refusal(
    home: Path, *, token: str | None = None, supervisor: int | None = None
) -> str:
    try:
        initial_env.write_initial_env(home, token=token, supervisor=supervisor)
    except ValueError as error:
        return str(error)
    return ""


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_new_file_is_created_at_home_env(tmp_path: Path) -> None:
    home = tmp_path / "bot home"
    env_path = initial_env.write_initial_env(home)
    assert env_path == home / ".env", "the file must be created as <home>/.env"


def test_new_file_is_readable_by_the_owner_only(tmp_path: Path) -> None:
    env_path = initial_env.write_initial_env(tmp_path / "home")
    expected = 0o600
    assert _mode(env_path) == expected, "the .env file must have mode 600"


def test_new_home_is_accessible_by_the_owner_only(tmp_path: Path) -> None:
    home = tmp_path / "nested" / "home"
    initial_env.write_initial_env(home)
    expected = 0o700
    assert _mode(home) == expected, "a new home directory must have mode 700"


def test_new_file_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    home = tmp_path / "home"
    initial_env.write_initial_env(home)
    expected = [".env"]
    assert [path.name for path in home.iterdir()] == expected, (
        "only .env may stay in the home directory"
    )


def test_existing_file_is_refused(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    with pytest.raises(FileExistsError) as caught:
        initial_env.write_initial_env(tmp_path)
    assert caught.value.filename2 == str(tmp_path / ".env"), (
        "the refusal must name the existing file"
    )


def test_existing_file_is_kept_unchanged(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("LLM_API_KEY=keep-this\n", encoding="utf-8")
    with contextlib.suppress(FileExistsError):
        initial_env.write_initial_env(tmp_path)
    observed = (env_path.read_text(encoding="utf-8"), sorted(tmp_path.iterdir()))
    expected = ("LLM_API_KEY=keep-this\n", [env_path])
    assert observed == expected, "a refused write must leave the directory unchanged"


def test_existing_symlink_is_not_followed(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere.txt"
    target.write_text("do not touch\n", encoding="utf-8")
    (tmp_path / ".env").symlink_to(target)
    with contextlib.suppress(FileExistsError):
        initial_env.write_initial_env(tmp_path)
    expected = "do not touch\n"
    assert target.read_text(encoding="utf-8") == expected, (
        "the target of a .env symlink must not be overwritten"
    )


def test_force_replaces_the_old_content(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    env_path = initial_env.write_initial_env(tmp_path, force=True)
    assert env_path.read_text(encoding="utf-8") == initial_env.load_env_template(), (
        "force must write a fresh template"
    )


def test_force_makes_a_world_readable_file_private(tmp_path: Path) -> None:
    old = tmp_path / ".env"
    old.write_text("SECRET=1\n", encoding="utf-8")
    old.chmod(0o644)
    env_path = initial_env.write_initial_env(tmp_path, force=True)
    expected = 0o600
    assert _mode(env_path) == expected, "the replaced file must have mode 600"


@pytest.mark.parametrize(
    ("token", "supervisor", "expected_line"),
    [
        ("123456789:" + "A" * 35, None, "BOT_TOKEN=123456789:" + "A" * 35),
        (None, 42, "SUPERVISOR_ID=42"),
        (None, 2**52 + 7, f"SUPERVISOR_ID={2**52 + 7}"),
    ],
    ids=["token", "supervisor", "large-supervisor"],
)
def test_given_value_replaces_its_placeholder(
    tmp_path: Path, token: str | None, supervisor: int | None, expected_line: str
) -> None:
    env_path = initial_env.write_initial_env(
        tmp_path, token=token, supervisor=supervisor
    )
    lines = env_path.read_text(encoding="utf-8").splitlines()
    assert expected_line in lines, "the value must replace the placeholder"


@pytest.mark.parametrize(
    "placeholder",
    [initial_env.BOT_PLACEHOLDER_LINE, initial_env.SUPERVISOR_PLACEHOLDER],
    ids=["token", "supervisor"],
)
def test_placeholder_remains_when_its_value_is_not_given(
    tmp_path: Path, placeholder: str
) -> None:
    content = initial_env.write_initial_env(tmp_path).read_text(encoding="utf-8")
    assert placeholder in content, "a missing value must keep its placeholder"


@pytest.mark.parametrize(
    "token",
    [
        "bad\nBOT_TOKEN=x",
        "123456789:" + "A" * 35 + "\nLLM_API_KEY=stolen",
        "123456789:" + "A" * 34 + " ",
        "",
        "not-a-token",
        "123456789:" + "A" * 35 + "\r",
    ],
    ids=[
        "line-injection",
        "valid-then-injection",
        "trailing-space",
        "empty",
        "words",
        "carriage-return",
    ],
)
def test_invalid_token_is_rejected(tmp_path: Path, token: str) -> None:
    expected = "The Telegram token has an invalid format."
    assert _refusal(tmp_path, token=token) == expected, "an invalid token is refused"


@pytest.mark.parametrize("supervisor", [0, -1, -(2**63)], ids=["zero", "-1", "min"])
def test_invalid_supervisor_is_rejected(tmp_path: Path, supervisor: int) -> None:
    expected = "The supervisor ID must be a positive integer."
    assert _refusal(tmp_path, supervisor=supervisor) == expected, (
        "a non-positive supervisor must be refused"
    )


def test_invalid_value_creates_no_file(tmp_path: Path) -> None:
    home = tmp_path / "home"
    injection_value = "bad\nBOT_TOKEN=x"
    _refusal(home, token=injection_value)
    assert not home.exists(), "a refused value must not create the home directory"


def test_packaged_template_matches_the_repository_example() -> None:
    example = Path(__file__).resolve().parents[2] / ".env.example"
    assert initial_env.load_env_template() == example.read_text(encoding="utf-8"), (
        "the packaged template must match .env.example"
    )
