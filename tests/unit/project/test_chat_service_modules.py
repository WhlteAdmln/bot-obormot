# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for project chat service modules."""

from bot_obormot.services.chat import incoming_log, reporting
from bot_obormot.services.chat import pipeline as chat_pipeline
from bot_obormot.services.chat.aggregation import aggregator as aggregator_module
from bot_obormot.services.chat.errors import handler as chat_error_handler


def test_chat_services_are_loaded_from_canonical_modules() -> None:
    """Chat services are loaded from canonical modules."""
    assert incoming_log.__name__ == "bot_obormot.services.chat.incoming_log"
    assert chat_pipeline.__name__ == "bot_obormot.services.chat.pipeline"
    assert reporting.__name__ == "bot_obormot.services.chat.reporting"
    assert chat_error_handler.__name__ == "bot_obormot.services.chat.errors.handler"
    expected_name = "bot_obormot.services.chat.aggregation.aggregator"
    assert aggregator_module.__name__ == expected_name
