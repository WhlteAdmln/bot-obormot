# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Personal system prompt and history limit operations of the database facade."""

from bot_obormot.services.database.decorators import handle_database_errors
from bot_obormot.services.database.facade.core import DatabaseCore
from bot_obormot.services.database.repositories import (
    history_limits as history_limits_repository,
)
from bot_obormot.services.database.repositories import (
    user_settings as user_settings_repository,
)


class UserSettingsOperations(DatabaseCore):
    """Personal system prompts and individual history limits."""

    @handle_database_errors
    async def get_system_prompt(self, user_id: int) -> str:
        """Return the personal prompt or the default system prompt."""
        prompt = await user_settings_repository.get_system_prompt(
            self._conn,
            user_id,
        )
        return prompt if prompt is not None else self.settings.DEFAULT_SYSTEM_PROMPT

    @handle_database_errors
    async def get_user_system_prompt(self, user_id: int) -> str | None:
        """Return the user's personal prompt or None."""
        return await user_settings_repository.get_system_prompt(
            self._conn,
            user_id,
        )

    @handle_database_errors
    async def delete_system_prompt(self, user_id: int) -> None:
        """Delete the user's personal system prompt."""
        await user_settings_repository.delete_system_prompt(
            self._conn,
            user_id,
        )

    @handle_database_errors
    async def set_system_prompt(
        self,
        user_id: int,
        prompt: str,
    ) -> None:
        """Save the user's personal system prompt."""
        await user_settings_repository.set_system_prompt(
            self._conn,
            user_id,
            prompt,
        )

    @handle_database_errors
    async def get_history_limit(self, user_id: int) -> int:
        """Return the individual history limit or the default value."""
        exchange_limit = await history_limits_repository.get_history_limit(
            self._conn,
            user_id,
        )
        return (
            self.settings.DEFAULT_HISTORY_EXCHANGES
            if exchange_limit is None
            else exchange_limit
        )

    @handle_database_errors
    async def set_history_limit(
        self,
        user_id: int,
        exchange_limit: int,
    ) -> None:
        """Set the individual history limit."""
        if not 1 <= exchange_limit <= self.settings.MAX_HISTORY_EXCHANGES:
            msg = "Invalid history limit."
            raise ValueError(msg)

        await history_limits_repository.set_history_limit(
            self._conn,
            user_id,
            exchange_limit,
        )

    @handle_database_errors
    async def delete_history_limit(self, user_id: int) -> None:
        """Delete the individual history limit."""
        await history_limits_repository.delete_history_limit(
            self._conn,
            user_id,
        )


__all__ = ["UserSettingsOperations"]
