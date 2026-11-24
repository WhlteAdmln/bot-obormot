# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the program runner."""

import os
from pathlib import Path

import pytest

from bot_obormot.common import process
from tests.support.program_runs import FakeProgramRun


def _refusal(name: str, arguments: list[str]) -> str:
    try:
        process.run_program(name, arguments)
    except ValueError as error:
        return str(error)
    return ""


@pytest.fixture(name="fake_run")
def fixture_fake_run(monkeypatch: pytest.MonkeyPatch) -> FakeProgramRun:
    """Resolve every program under /srv/tools and exit with code 7."""
    monkeypatch.setattr(process.shutil, "which", lambda name: f"/srv/tools/{name}")
    fake = FakeProgramRun(returncode=7)
    monkeypatch.setattr(process.subprocess, "run", fake)
    return fake


def test_run_program_starts_the_resolved_program_with_its_arguments(
    fake_run: FakeProgramRun,
) -> None:
    process.run_program("pandoc", ["--from", "rst", "notes.rst"])
    expected = [["/srv/tools/pandoc", "--from", "rst", "notes.rst"]]
    assert fake_run.commands == expected, "argv must start with the resolved path"


def test_run_program_returns_the_finished_process(fake_run: FakeProgramRun) -> None:
    _ = fake_run
    result = process.run_program("sox", ["--version"])
    expected_code = 7
    assert result.returncode == expected_code, "the exit code must be returned"


def test_run_program_passes_the_run_options(
    fake_run: FakeProgramRun, tmp_path: Path
) -> None:
    process.run_program(
        "magick",
        ["identify", "cat.png"],
        cwd=tmp_path,
        timeout=4.5,
        capture_output=True,
    )
    expected = [
        {
            "capture_output": True,
            "timeout": 4.5,
            "check": False,
            "cwd": tmp_path,
            "env": None,
        }
    ]
    assert fake_run.options == expected, "options must reach subprocess.run unchanged"


def test_run_program_never_raises_on_a_failed_exit_by_default(
    fake_run: FakeProgramRun,
) -> None:
    process.run_program("tar", ["-tf", "backup.tar"])
    expected = [
        {
            "capture_output": False,
            "timeout": None,
            "check": False,
            "cwd": None,
            "env": None,
        }
    ]
    assert fake_run.options == expected, "the default run must not check the exit code"


@pytest.mark.parametrize(
    "name",
    [
        "",
        "/usr/bin/ffmpeg",
        "bin/ffprobe",
        "-rf",
        "sys\0temctl",
        "../ffmpeg",
    ],
    ids=[
        "empty",
        "absolute",
        "relative",
        "option",
        "nul",
        "parent",
    ],
)
def test_run_program_rejects_a_name_that_is_not_a_bare_program(
    fake_run: FakeProgramRun, name: str
) -> None:
    _ = fake_run
    assert _refusal(name, ["--help"]) == f"Invalid program name: {name!r}", (
        "only a bare program name may run"
    )


@pytest.mark.parametrize(
    "arguments",
    [["-i", "clip\0.webm"], ["\0"], ["ok", "-y", "x\0; rm -rf /"]],
    ids=["inside", "alone", "after-valid-arguments"],
)
def test_run_program_rejects_a_nul_byte_in_an_argument(
    fake_run: FakeProgramRun, arguments: list[str]
) -> None:
    _ = fake_run
    expected = "Argument of ffmpeg contains a NUL byte"
    assert _refusal("ffmpeg", arguments) == expected, (
        "an argument with a NUL byte must be refused"
    )


def test_run_program_does_not_start_anything_for_an_invalid_argv(
    fake_run: FakeProgramRun,
) -> None:
    _refusal("ffprobe", ["movie.mp4\0"])
    expected_empty: list[list[str]] = []
    assert fake_run.commands == expected_empty, "an invalid argv must not run"


def test_resolve_program_reports_a_missing_program(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(process.shutil, "which", lambda _name: None)
    with pytest.raises(FileNotFoundError) as caught:
        process.resolve_program("lilypond")
    expected = "lilypond was not found on this system."
    assert str(caught.value) == expected, "a missing program must be named"


def test_resolve_program_returns_an_absolute_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(process.shutil, "which", lambda _name: "local/gifsicle")
    expected = str(tmp_path / "local" / "gifsicle")
    actual = process.resolve_program("gifsicle")
    assert actual == expected, "a relative PATH hit must become absolute"


def test_run_program_narrows_path_to_the_program_directory_and_defpath(
    fake_run: FakeProgramRun,
) -> None:
    process.run_program("ffprobe", ["clip.mp4"], narrow_path=True)
    path = str(fake_run.options[0]["env"]["PATH"])
    expected = os.pathsep.join(("/srv/tools", os.defpath))
    assert path == expected, "PATH must hold the tool directory and defpath only"
