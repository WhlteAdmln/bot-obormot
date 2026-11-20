# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Chat pipeline: context fitting, LLM streaming and saving the exchange."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bot_obormot.errors import LLMEmptyResponseError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from bot_obormot.services.database import Database
    from bot_obormot.services.llm.client import LLMClient

logger = logging.getLogger("bot_obormot.services.chat.pipeline")


@dataclass(frozen=True, slots=True)
class ChatPipelineDependencies:
    """Holds the shared services required by chat processing."""

    llm_client: LLMClient
    database: Database


# Longer histories create additional requests during context fitting.
MAX_CONTEXT_EXCHANGES = 100


async def process_chat(
    user_id: int,
    user_content: str,
    saved_user_text: str,
    media: list[bytes] | None = None,
    on_update: Callable[[str], Awaitable[None]] | None = None,
    *,
    dependencies: ChatPipelineDependencies,
) -> str:
    """Builds the context, streams the LLM reply and saves the exchange.

    Fit the context to the token limit, retrieve the LLM response, and save
    the complete exchange to the database.

    ``on_update`` is an optional callback that receives the accumulated text
    during generation.
    """
    system_prompt = await dependencies.database.get_system_prompt(user_id)

    # Retrieve the user's individual history limit.
    # Use the default limit when no setting is available.
    history_limit = min(
        await dependencies.database.get_history_limit(user_id),
        MAX_CONTEXT_EXCHANGES,
    )

    # The limit now represents complete exchanges rather than individual messages.
    history = await dependencies.database.get_history(
        user_id,
        limit=history_limit,
    )

    messages = await dependencies.llm_client.fit_messages_to_context(
        system_prompt=system_prompt,
        history=history,
        user_message=user_content,
    )

    response_parts = []

    async for token in dependencies.llm_client.stream(messages):
        response_parts.append(token)

        if on_update is not None:
            await on_update("".join(response_parts))

    response = "".join(response_parts).strip()

    if not response:
        raise LLMEmptyResponseError

    await dependencies.database.add_exchange(
        user_id,
        saved_user_text,
        response,
        media=media,
    )

    try:
        await dependencies.database.prune_history(user_id)
    except Exception:
        logger.warning(
            "History pruning failed for user_id=%s",
            user_id,
            exc_info=True,
        )

    return response
