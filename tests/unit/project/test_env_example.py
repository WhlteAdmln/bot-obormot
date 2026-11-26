# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Keep the shipped .env.example in sync with Config's environment inputs."""

from pathlib import Path

from scripts.docs_checks.settings import settings_environment_names


def _env_example_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".env.example"


def _env_example_names(path: Path) -> tuple[set[str], list[str]]:
    names: set[str] = set()
    duplicates: list[str] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        assignment_sign = "="
        if not stripped or stripped.startswith("#") or assignment_sign not in stripped:
            continue
        name = stripped.split("=", maxsplit=1)[0].strip()
        if name in names:
            duplicates.append(name)
        names.add(name)

    return names, duplicates


def test_env_example_has_no_duplicate_variables() -> None:
    _, duplicates = _env_example_names(_env_example_path())

    expected_empty: list[str] = []
    assert duplicates == expected_empty, (
        f"Duplicate variables in .env.example: {sorted(duplicates)}"
    )


def test_env_example_matches_config_environment_variables() -> None:
    settings_names = settings_environment_names()
    example_names, _ = _env_example_names(_env_example_path())

    assert example_names == settings_names, (
        f"Missing from .env.example: {sorted(settings_names - example_names)}; "
        f"not read by Settings: {sorted(example_names - settings_names)}"
    )
