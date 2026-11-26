# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for project chat service modules."""

from types import ModuleType

import pytest

from bot_obormot.services.chat import incoming_log, reporting
from bot_obormot.services.chat import pipeline as chat_pipeline
from bot_obormot.services.chat.aggregation import aggregator as aggregator_module
from bot_obormot.services.chat.errors import handler as chat_error_handler


@pytest.mark.parametrize(
    ("module", "expected_name"),
    [
        (incoming_log, "bot_obormot.services.chat.incoming_log"),
        (chat_pipeline, "bot_obormot.services.chat.pipeline"),
        (reporting, "bot_obormot.services.chat.reporting"),
        (chat_error_handler, "bot_obormot.services.chat.errors.handler"),
        (aggregator_module, "bot_obormot.services.chat.aggregation.aggregator"),
    ],
)
def test_chat_services_are_loaded_from_canonical_modules(
    module: ModuleType,
    expected_name: str,
) -> None:
    assert module.__name__ == expected_name, "chat service module was renamed"
