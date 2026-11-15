# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Aggregation of consecutive text messages from one user."""

import asyncio
import logging
import time

from aiogram.types import Message

from bot.services.chat.aggregation.config import (
    MESSAGE_AGGREGATION_WINDOW,
    MESSAGE_LENGTH_THRESHOLD,
)
from bot.services.chat.aggregation.state import _AggregationState
from bot.services.validation import MAX_INPUT_TEXT_LENGTH
from bot.utils.text import utf16_length

logger = logging.getLogger("bot.services.chat.aggregation.aggregator")
_utf16_length = utf16_length


class MessageAggregator:
    """Объединяет последовательные текстовые сообщения одного пользователя."""

    def __init__(self) -> None:
        """Creates empty per-user aggregation state."""
        self._states: dict[int, _AggregationState] = {}
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()

    async def collect(self, message: Message) -> str | None:
        """Returns the collected text, or None for a continuation part.

        Возвращает готовый текст либо None, если сообщение
        принято как продолжение предыдущего.
        """
        text = message.text

        if not text or message.from_user is None:
            return text

        user_id = message.from_user.id
        part_length = _utf16_length(text)
        now = time.monotonic()

        async with self._lock:
            state = self._states.get(user_id)

            if state is not None:
                elapsed = now - state.last_activity

                logger.info(
                    "Message aggregation: incoming part, "
                    "user_id=%s, length_utf16=%s, "
                    "interval=%.3fs, current_parts=%s",
                    user_id,
                    part_length,
                    elapsed,
                    len(state.parts),
                )

                is_continuation = elapsed <= MESSAGE_AGGREGATION_WINDOW

                if is_continuation:
                    collected = sum(len(part) for part in state.parts)

                    # Дальнейшие части не принимаем, если накопленный текст
                    # уже превысил допустимую длину. Итоговая валидация
                    # сообщит пользователю об ошибке длины.
                    if collected > MAX_INPUT_TEXT_LENGTH:
                        return None

                    state.parts.append(text)
                    state.last_activity = now
                    state.event.set()

                    logger.info(
                        "Message aggregation: part accepted, "
                        "user_id=%s, part_number=%s, length_utf16=%s",
                        user_id,
                        len(state.parts),
                        part_length,
                    )

                    return None

                # Время ожидания истекло.
                # Завершаем предыдущую сборку.
                self._states.pop(user_id, None)

                if state.future and not state.future.done():
                    state.future.set_result("\n".join(state.parts))

            else:
                logger.info(
                    "Message aggregation: incoming first part, "
                    "user_id=%s, length_utf16=%s",
                    user_id,
                    part_length,
                )

            # Короткие самостоятельные сообщения не задерживаем.
            if part_length < MESSAGE_LENGTH_THRESHOLD:
                logger.debug(
                    "Message aggregation: threshold not reached, "
                    "user_id=%s, length_utf16=%s, threshold=%s",
                    user_id,
                    part_length,
                    MESSAGE_LENGTH_THRESHOLD,
                )
                return text

            loop = asyncio.get_running_loop()
            future: asyncio.Future[str] = loop.create_future()

            state = _AggregationState(
                parts=[text],
                last_activity=now,
                future=future,
            )

            self._states[user_id] = state

            logger.info(
                "Message aggregation: started, "
                "user_id=%s, first_part_length_utf16=%s, "
                "threshold=%s, waiting=%.1fs",
                user_id,
                part_length,
                MESSAGE_LENGTH_THRESHOLD,
                MESSAGE_AGGREGATION_WINDOW,
            )

            task = asyncio.create_task(
                self._wait_for_continuation(user_id, state),
                name=f"message_aggregation_{user_id}",
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        # Отмена обработчика не отменяет общий Future.
        return await asyncio.shield(future)

    async def _wait_for_continuation(
        self,
        user_id: int,
        state: _AggregationState,
    ) -> None:
        """Ожидает продолжение и завершает сборку после таймаута."""
        try:
            while True:
                async with self._lock:
                    if self._states.get(user_id) is not state:
                        return

                    elapsed = time.monotonic() - state.last_activity
                    remaining = MESSAGE_AGGREGATION_WINDOW - elapsed

                    if remaining <= 0:
                        self._states.pop(user_id, None)

                        result = "\n".join(state.parts)

                        if state.future and not state.future.done():
                            state.future.set_result(result)

                        logger.info(
                            "Message aggregation: completed, "
                            "user_id=%s, parts=%s, characters=%s, "
                            "length_utf16=%s",
                            user_id,
                            len(state.parts),
                            len(result),
                            _utf16_length(result),
                        )

                        return

                    # Очищаем событие под блокировкой,
                    # чтобы не потерять сигнал от следующей части.
                    state.event.clear()

                try:
                    await asyncio.wait_for(
                        state.event.wait(),
                        timeout=remaining,
                    )

                except TimeoutError:
                    continue

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Message aggregation failed: user_id=%s",
                user_id,
            )

            async with self._lock:
                if self._states.get(user_id) is state:
                    self._states.pop(user_id, None)

                if state.future and not state.future.done():
                    state.future.set_result("\n".join(state.parts))


message_aggregator = MessageAggregator()
