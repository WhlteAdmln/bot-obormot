# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Chat pipeline: context fitting, LLM streaming and saving the exchange."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from bot.services.database import Database
    from bot.services.llm.client import LLMClient

logger = logging.getLogger("bot.services.chat.pipeline")


@dataclass(frozen=True, slots=True)
class ChatPipelineDependencies:
    """Holds the shared services required by chat processing."""

    llm_client: LLMClient
    database: Database


# Более длинная история создаёт лишние запросы при подгонке контекста.
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

    Формирует контекст с учётом лимита токенов,
    получает ответ от LLM и сохраняет полный обмен в БД.

    on_update — необязательный callback для передачи
    накопленного текста во время генерации.
    """
    system_prompt = await dependencies.database.get_system_prompt(user_id)

    # Получаем индивидуальный лимит пользователя.
    # Если настройки нет, используется стандартный лимит.
    history_limit = min(
        await dependencies.database.get_history_limit(user_id),
        MAX_CONTEXT_EXCHANGES,
    )

    # limit теперь означает количество полных обменов,
    # а не количество отдельных сообщений.
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
        msg = "LLM вернула пустой ответ."
        raise RuntimeError(msg)

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
