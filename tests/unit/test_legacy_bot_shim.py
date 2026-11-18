# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the deprecated ``python -m bot.main`` compatibility shim."""

import runpy
import sys

import pytest

from bot import main as legacy_main
from bot_obormot import cli


def test_shim_prints_one_deprecation_line_and_runs_the_bot(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The old entry point warns on stderr and forwards to ``run``."""
    calls: list[list[str]] = []

    def fake_cli_main(argv: list[str]) -> int:
        calls.append(argv)
        return 0

    monkeypatch.setattr(legacy_main, "cli_main", fake_cli_main)

    assert legacy_main.main() == 0

    captured = capsys.readouterr()
    assert calls == [["run"]]
    assert captured.out == ""
    assert captured.err.splitlines() == [legacy_main.DEPRECATION_MESSAGE]
    assert "0.3.0" in legacy_main.DEPRECATION_MESSAGE


def test_python_dash_m_bot_main_reaches_the_new_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Old systemd units (``python -m bot.main``) still start the new ``run``."""
    calls: list[list[str]] = []
    monkeypatch.setattr(cli, "main", lambda argv: calls.append(list(argv)) or 0)
    monkeypatch.delitem(sys.modules, "bot.main", raising=False)

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("bot.main", run_name="__main__")

    assert exit_info.value.code == 0
    assert calls == [["run"]]
    assert "DEPRECATED" in capsys.readouterr().err
