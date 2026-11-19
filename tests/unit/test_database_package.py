# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for database package."""

from pathlib import Path

import bot_obormot.services.database as database_package
import bot_obormot.services.database.facade as facade_module
from bot_obormot.services.database import (
    MAX_HISTORY_IMAGES,
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
from bot_obormot.services.database.facade import (
    handle_database_errors as facade_decorator,
)
from bot_obormot.services.database.facade import (
    read_image_as_base64 as facade_image_reader,
)
from bot_obormot.services.database.files.image_storage import (
    read_image_as_base64 as canonical_image_reader,
)
from tests.support.settings import make_settings


def test_database_package_reexports_facade_api_without_global_instance() -> None:
    """Database package reexports the facade API without a global instance."""
    assert Database is FacadeDatabase
    assert not hasattr(database_package, "db")
    assert not hasattr(facade_module, "db")
    assert MAX_HISTORY_IMAGES == 3
    assert callable(handle_database_errors)
    assert callable(read_image_as_base64)


def test_database_images_dir_uses_injected_settings_at_instance_creation(
    tmp_path: Path,
) -> None:
    """Database images dir uses injected settings at instance creation."""
    database_path = tmp_path / "custom" / "history.db"
    settings = make_settings(DATABASE_PATH=str(database_path))

    database = Database(settings)

    assert database.images_dir == database_path.resolve().parent / "images"


def test_database_instance_does_not_create_files_before_connect(
    tmp_path: Path,
) -> None:
    """Database instance does not create files before connect."""
    database_path = tmp_path / "not-created" / "history.db"
    settings = make_settings(DATABASE_PATH=str(database_path))

    Database(settings)

    assert not database_path.parent.exists()


def test_database_helpers_are_reexported_from_their_new_modules() -> None:
    """Database helpers are reexported from their new modules."""
    assert handle_database_errors is canonical_decorator is facade_decorator
    assert read_image_as_base64 is canonical_image_reader is facade_image_reader
