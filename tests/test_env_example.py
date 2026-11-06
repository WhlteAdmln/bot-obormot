"""Keep the shipped .env.example in sync with Config's environment inputs."""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "bot" / "config" / "settings.py"
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"

_ENV_HELPER_NAMES = {
    "get_bool",
    "get_float",
    "get_int",
    "get_optional_int",
    "parse_ids",
}


def _config_environment_names() -> set[str]:
    tree = ast.parse(CONFIG_PATH.read_text(encoding="utf-8"))
    config_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Config"
    )
    names: set[str] = set()

    for node in ast.walk(config_class):
        if not isinstance(node, ast.Call):
            continue

        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == "os"
            and function.attr == "getenv"
        ):
            if node.args and isinstance(node.args[0], ast.Constant):
                if isinstance(node.args[0].value, str):
                    names.add(node.args[0].value)
            continue

        if isinstance(function, ast.Name) and function.id == "get_log_level":
            names.add("LOG_LEVEL")
            continue

        if isinstance(function, ast.Name) and function.id in _ENV_HELPER_NAMES:
            if node.args and isinstance(node.args[0], ast.Constant):
                if isinstance(node.args[0].value, str):
                    names.add(node.args[0].value)

    return names


def _env_example_names() -> tuple[set[str], list[str]]:
    names: set[str] = set()
    duplicates: list[str] = []

    for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name = stripped.split("=", maxsplit=1)[0].strip()
        if name in names:
            duplicates.append(name)
        names.add(name)

    return names, duplicates


def test_env_example_matches_config_environment_variables():
    config_names = _config_environment_names()
    example_names, duplicates = _env_example_names()

    assert not duplicates, f"Duplicate variables in .env.example: {sorted(duplicates)}"
    assert example_names == config_names, (
        f"Missing from .env.example: {sorted(config_names - example_names)}; "
        f"not read by Config: {sorted(example_names - config_names)}"
    )
