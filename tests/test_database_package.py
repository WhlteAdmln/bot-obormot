# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

from bot.config import config
from bot.services.database import (
    MAX_HISTORY_IMAGES,
    Database,
    db,
    handle_database_errors,
    read_image_as_base64,
)
from bot.services.database.facade import (
    Database as FacadeDatabase,
)
from bot.services.database.facade import (
    db as facade_db,
)


def test_database_package_reexports_same_facade_objects():
    assert Database is FacadeDatabase
    assert db is facade_db
    assert isinstance(db, Database)
    assert MAX_HISTORY_IMAGES == 3
    assert callable(handle_database_errors)
    assert callable(read_image_as_base64)


def test_database_images_dir_uses_config_at_instance_creation(tmp_path, monkeypatch):
    database_path = tmp_path / "custom" / "history.db"
    monkeypatch.setattr(config, "DATABASE_PATH", str(database_path))

    database = Database()

    assert database.images_dir == database_path.resolve().parent / "images"


def test_database_instance_does_not_create_files_before_connect(tmp_path, monkeypatch):
    database_path = tmp_path / "not-created" / "history.db"
    monkeypatch.setattr(config, "DATABASE_PATH", str(database_path))

    Database()

    assert not database_path.parent.exists()


def test_database_helpers_are_reexported_from_their_new_modules():
    from bot.services.database.decorators import (
        handle_database_errors as canonical_decorator,
    )
    from bot.services.database.facade import (
        handle_database_errors as facade_decorator,
    )
    from bot.services.database.facade import (
        read_image_as_base64 as facade_image_reader,
    )
    from bot.services.database.files.image_storage import (
        read_image_as_base64 as canonical_image_reader,
    )

    assert handle_database_errors is canonical_decorator is facade_decorator
    assert read_image_as_base64 is canonical_image_reader is facade_image_reader
