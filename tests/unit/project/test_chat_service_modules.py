# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for project chat service modules."""

from bot_obormot.services.chat import incoming_log, reporting
from bot_obormot.services.chat import pipeline as chat_pipeline
from bot_obormot.services.chat.aggregation import aggregator as aggregator_module
from bot_obormot.services.chat.errors import handler as chat_error_handler


def test_chat_services_are_loaded_from_canonical_modules() -> None:
    """Chat services are loaded from canonical modules."""
    expected_name_2 = "bot_obormot.services.chat.incoming_log"
    assert incoming_log.__name__ == expected_name_2
    expected_name_2 = "bot_obormot.services.chat.pipeline"
    assert chat_pipeline.__name__ == expected_name_2
    expected_name_2 = "bot_obormot.services.chat.reporting"
    assert reporting.__name__ == expected_name_2
    expected_name_2 = "bot_obormot.services.chat.errors.handler"
    assert chat_error_handler.__name__ == expected_name_2
    expected_name = "bot_obormot.services.chat.aggregation.aggregator"
    assert aggregator_module.__name__ == expected_name
