# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Check at dispatcher startup that handlers get every dependency they need."""

REQUIRED_DEPENDENCIES = ("settings", "llm_client", "database")


async def check_dependencies(**workflow_data: object) -> None:
    """Stop the startup when the workflow data lacks a handler dependency."""
    missing = [
        name for name in REQUIRED_DEPENDENCIES if workflow_data.get(name) is None
    ]
    if missing:
        msg = f"Dispatcher is missing handler dependencies: {', '.join(missing)}"
        raise RuntimeError(msg)
