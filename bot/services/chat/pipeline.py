import logging
from collections.abc import Awaitable, Callable

from bot.services.database import db
from bot.services.llm import llm_client

logger = logging.getLogger("bot.services.chat_processing")


async def process_chat(
    user_id: int,
    user_content: str,
    saved_user_text: str,
    media: list[bytes] | None = None,
    on_update: Callable[[str], Awaitable[None]] | None = None,
) -> str:
    """
    Формирует контекст с учётом лимита токенов,
    получает ответ от LLM и сохраняет полный обмен в БД.

    on_update — необязательный callback для передачи
    накопленного текста во время генерации.
    """

    system_prompt = await db.get_system_prompt(user_id)

    # Получаем индивидуальный лимит пользователя.
    # Если настройки нет, используется стандартный лимит.
    history_limit = await db.get_history_limit(user_id)

    # limit теперь означает количество полных обменов,
    # а не количество отдельных сообщений.
    history = await db.get_history(
        user_id,
        limit=history_limit,
    )

    messages = await llm_client.fit_messages_to_context(
        system_prompt=system_prompt,
        history=history,
        user_message=user_content,
    )

    response_parts = []

    async for token in llm_client.stream(messages):
        response_parts.append(token)

        if on_update is not None:
            await on_update("".join(response_parts))

    response = "".join(response_parts).strip()

    if not response:
        raise RuntimeError("LLM вернула пустой ответ.")

    await db.add_exchange(
        user_id,
        saved_user_text,
        response,
        media=media,
    )

    return response
