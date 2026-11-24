# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the public API of the database package."""

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


def test_database_package_reexports_facade_api_without_global_instance() -> None:
    assert Database is FacadeDatabase
    assert not hasattr(database_package, "db")
    assert not hasattr(facade_module, "db")
    expected_number = 3
    assert expected_number == MAX_HISTORY_MEDIA_MESSAGES
    assert callable(handle_database_errors)
    assert callable(read_image_as_base64)


def test_database_helpers_are_reexported_from_their_new_modules() -> None:
    assert handle_database_errors is canonical_decorator
    assert read_image_as_base64 is canonical_image_reader
