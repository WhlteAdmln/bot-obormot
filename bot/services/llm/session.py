"""Создание и повторное использование HTTP-сессии LLM-клиента."""

import aiohttp

from bot.config import config


async def get_session(client) -> aiohttp.ClientSession:
    """Возвращает открытую HTTP-сессию, создавая её при необходимости."""
    if client.session is None or client.session.closed:
        timeout = aiohttp.ClientTimeout(total=config.LLM_TIMEOUT)
        client.session = aiohttp.ClientSession(timeout=timeout)

    return client.session
