# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the public API of the database package."""

from types import ModuleType

import pytest

import bot_obormot.services.database as database_package
import bot_obormot.services.database.facade as facade_module
from bot_obormot.services.database import (
    MAX_HISTORY_MEDIA_MESSAGES,
    Database,
    handle_database_errors,
    read_image_as_base64,
)
from bot_obormot.services.database.decorators import (
    handle_database_errors as canonical_decorator,
)
from bot_obormot.services.database.facade import (
    Database as FacadeDatabase,
)
from bot_obormot.services.database.files.image_storage import (
    read_image_as_base64 as canonical_image_reader,
)


def test_database_package_reexports_the_facade_database() -> None:
    assert Database is FacadeDatabase, "the package exports another Database"


@pytest.mark.parametrize("module", [database_package, facade_module])
def test_database_modules_define_no_global_instance(module: ModuleType) -> None:
    instance_name = "db"
    assert not hasattr(module, instance_name), "a global database instance exists"


def test_database_package_exports_the_history_media_limit() -> None:
    expected_limit = 3
    assert expected_limit == MAX_HISTORY_MEDIA_MESSAGES, "the media limit differs"


def test_database_package_reexports_the_error_decorator() -> None:
    assert handle_database_errors is canonical_decorator, "another decorator exported"


def test_database_package_reexports_the_image_reader() -> None:
    assert read_image_as_base64 is canonical_image_reader, "another reader exported"
