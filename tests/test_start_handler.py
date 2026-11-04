from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.config import config
from bot.handlers.start.handler import cmd_start
from bot.services.database import db


@pytest.mark.asyncio
async def test_start_help_and_command_menu_include_forget_me(monkeypatch):
    monkeypatch.setattr(config, "SUPERVISOR_ID", 999999999)
    monkeypatch.setattr(db, "get_admin_ids", AsyncMock(return_value=set()))

    user_id = 123456789
    response = SimpleNamespace(message_id=42)
    answer = AsyncMock(return_value=response)
    set_my_commands = AsyncMock()
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        chat=SimpleNamespace(id=user_id),
        bot=SimpleNamespace(set_my_commands=set_my_commands),
        answer=answer,
    )
    state = SimpleNamespace(update_data=AsyncMock())

    await cmd_start(message, state)

    commands = set_my_commands.await_args.kwargs["commands"]
    assert any(command.command == "forget_me" for command in commands)
    assert "/forget_me — удалить все свои данные" in answer.await_args.args[0]


@pytest.mark.asyncio
async def test_start_adds_ban_commands_for_admins(monkeypatch):
    monkeypatch.setattr(config, "SUPERVISOR_ID", 999999999)
    admin_id = 111111111
    monkeypatch.setattr(db, "get_admin_ids", AsyncMock(return_value={admin_id}))

    response = SimpleNamespace(message_id=42)
    answer = AsyncMock(return_value=response)
    set_my_commands = AsyncMock()
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=admin_id),
        chat=SimpleNamespace(id=admin_id),
        bot=SimpleNamespace(set_my_commands=set_my_commands),
        answer=answer,
    )
    state = SimpleNamespace(update_data=AsyncMock())

    await cmd_start(message, state)

    commands = {
        command.command for command in set_my_commands.await_args.kwargs["commands"]
    }
    assert {"ban", "unban"} <= commands
    help_text = answer.await_args.args[0]
    assert "/ban ID — заблокировать пользователя" in help_text
    assert "/unban ID — снять блокировку пользователя" in help_text
