# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Aggregation of consecutive text messages from one user."""

import asyncio
import logging
import time

from aiogram.types import Message

from bot_obormot.common.text import utf16_length
from bot_obormot.common.validation import MAX_INPUT_TEXT_LENGTH
from bot_obormot.services.chat.aggregation.config import (
    MESSAGE_AGGREGATION_WINDOW,
    MESSAGE_LENGTH_THRESHOLD,
)
from bot_obormot.services.chat.aggregation.state import _AggregationState

logger = logging.getLogger("bot_obormot.services.chat.aggregation.aggregator")
_utf16_length = utf16_length


class MessageAggregator:
    """Aggregate consecutive text messages from one user."""

    def __init__(self) -> None:
        """Create empty per-user aggregation state."""
        self._states: dict[int, _AggregationState] = {}
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()

    async def collect(self, message: Message) -> str | None:
        """Return collected text or None for a continuation part.

        Return None when the message is accepted as a continuation.
        """
        text = message.text

        if not text or message.from_user is None:
            return text

        user_id = message.from_user.id
        part_length = _utf16_length(text)
        now = time.monotonic()

        async with self._lock:
            state = self._states.get(user_id)

            if state is None:
                logger.info(
                    "Message aggregation: incoming first part, "
                    "user_id=%s, length_utf16=%s",
                    user_id,
                    part_length,
                )
            elif self._absorb_continuation(user_id, state, text, part_length, now):
                return None

            # Do not delay short standalone messages.
            if part_length < MESSAGE_LENGTH_THRESHOLD:
                logger.debug(
                    "Message aggregation: threshold not reached, "
                    "user_id=%s, length_utf16=%s, threshold=%s",
                    user_id,
                    part_length,
                    MESSAGE_LENGTH_THRESHOLD,
                )
                return text

            future = self._start_aggregation(user_id, text, part_length, now)

        # Cancelling the handler does not cancel the shared future.
        return await asyncio.shield(future)

    def _absorb_continuation(
        self,
        user_id: int,
        state: _AggregationState,
        text: str,
        part_length: int,
        now: float,
    ) -> bool:
        """Add a part to the active aggregation; return False if it expired."""
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

        if elapsed <= MESSAGE_AGGREGATION_WINDOW:
            collected = sum(len(part) for part in state.parts)

            # Final validation notifies the user about an oversized text.
            if collected > MAX_INPUT_TEXT_LENGTH:
                return True

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
            return True

        # The wait window has expired. Complete the previous aggregation.
        self._states.pop(user_id, None)

        if state.future and not state.future.done():
            state.future.set_result("\n".join(state.parts))
        return False

    def _start_aggregation(
        self,
        user_id: int,
        text: str,
        part_length: int,
        now: float,
    ) -> asyncio.Future[str]:
        """Register a new aggregation and its waiter task; the lock is held."""
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
        return future

    async def _remaining_wait(
        self,
        user_id: int,
        state: _AggregationState,
    ) -> float | None:
        """Return the time left in the window, or None once aggregation ended."""
        async with self._lock:
            if self._states.get(user_id) is not state:
                return None

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

                return None

            # Clear the event while holding the lock
            # to avoid missing a signal from the next part.
            state.event.clear()
            return remaining

    async def _abort_aggregation(self, user_id: int, state: _AggregationState) -> None:
        """Release waiters with the text collected so far after a failure."""
        async with self._lock:
            if self._states.get(user_id) is state:
                self._states.pop(user_id, None)

            if state.future and not state.future.done():
                state.future.set_result("\n".join(state.parts))

    async def _wait_for_continuation(
        self,
        user_id: int,
        state: _AggregationState,
    ) -> None:
        """Wait for continuation and finalize aggregation after the timeout."""
        try:
            while True:
                remaining = await self._remaining_wait(user_id, state)
                if remaining is None:
                    return

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
            await self._abort_aggregation(user_id, state)
