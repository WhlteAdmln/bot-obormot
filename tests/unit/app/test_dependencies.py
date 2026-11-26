# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the dispatcher dependency check."""

import asyncio

import pytest

from bot_obormot.app.dependencies import REQUIRED_DEPENDENCIES, check_dependencies


@pytest.mark.parametrize("missing", REQUIRED_DEPENDENCIES)
def test_check_dependencies_names_the_missing_dependency(missing: str) -> None:
    workflow_data: dict[str, object] = {
        name: object() for name in REQUIRED_DEPENDENCIES if name != missing
    }
    workflow_data["bots"] = ["Ёлка-бот №7"]
    expected = f"Dispatcher is missing handler dependencies: {missing}"

    with pytest.raises(RuntimeError) as error:
        asyncio.run(check_dependencies(**workflow_data))

    assert str(error.value) == expected, "the error names another dependency"


def test_check_dependencies_treats_none_as_missing() -> None:
    workflow_data: dict[str, object] = dict.fromkeys(REQUIRED_DEPENDENCIES, 41.5)
    workflow_data["database"] = None
    expected = "Dispatcher is missing handler dependencies: database"

    with pytest.raises(RuntimeError) as error:
        asyncio.run(check_dependencies(**workflow_data))

    assert str(error.value) == expected, "a None dependency is not reported"


def test_check_dependencies_lists_every_missing_dependency() -> None:
    workflow_data: dict[str, object] = {"settings": "Настройки_Δ"}
    expected = "Dispatcher is missing handler dependencies: llm_client, database"

    with pytest.raises(RuntimeError) as error:
        asyncio.run(check_dependencies(**workflow_data))

    assert str(error.value) == expected, "the error misses a dependency"
