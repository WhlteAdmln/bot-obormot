# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Keep the shipped .env.example in sync with Config's environment inputs."""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SETTINGS_PATH = PROJECT_ROOT / "bot_obormot" / "config" / "model" / "loader.py"
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"

_ENV_READER_NAMES = {
    "read_bool",
    "read_float",
    "read_ids",
    "read_int",
    "read_optional_int",
    "read_str",
}


def _settings_environment_names() -> set[str]:
    tree = ast.parse(SETTINGS_PATH.read_text(encoding="utf-8"))
    expected_name = "_SettingsLoader"
    settings_loader = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == expected_name
    )
    names: set[str] = set()

    for node in ast.walk(settings_loader):
        if not isinstance(node, ast.Call):
            continue

        function = node.func
        expected_id = "get_log_level"
        if isinstance(function, ast.Name) and function.id == expected_id:
            names.add("LOG_LEVEL")
            continue

        if (
            isinstance(function, ast.Attribute)
            and function.attr in _ENV_READER_NAMES
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)

    return names


def _env_example_names() -> tuple[set[str], list[str]]:
    names: set[str] = set()
    duplicates: list[str] = []

    for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        assignment_sign = "="
        if not stripped or stripped.startswith("#") or assignment_sign not in stripped:
            continue
        name = stripped.split("=", maxsplit=1)[0].strip()
        if name in names:
            duplicates.append(name)
        names.add(name)

    return names, duplicates


def test_env_example_matches_config_environment_variables() -> None:
    settings_names = _settings_environment_names()
    example_names, duplicates = _env_example_names()

    expected_empty = []
    assert duplicates == expected_empty, (
        f"Duplicate variables in .env.example: {sorted(duplicates)}"
    )
    assert example_names == settings_names, (
        f"Missing from .env.example: {sorted(settings_names - example_names)}; "
        f"not read by Settings: {sorted(example_names - settings_names)}"
    )
