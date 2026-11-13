# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

import logging
from types import SimpleNamespace

import pytest

from bot.config import config
from bot.handlers.admin import handler as admin_handler
from bot.handlers.history import limits as history_limits_handler


class FakeMessage:
    def __init__(self, user_id: int):
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []

    async def answer(self, text: str, **kwargs):
        self.answers.append(text)


@pytest.mark.asyncio
async def test_admin_add_writes_audit_record(monkeypatch, caplog):
    actor_id = config.SUPERVISOR_ID
    target_id = 123456789

    async def add_admin(user_id):
        assert user_id == target_id
        return True

    monkeypatch.setattr(admin_handler.db, "add_admin", add_admin)
    message = FakeMessage(actor_id)
    command = SimpleNamespace(args=str(target_id))

    with caplog.at_level(logging.INFO, logger="bot.audit"):
        await admin_handler.cmd_admin_add(message, command)

    assert (
        f"AUDIT action=admin_add actor={actor_id} target={target_id} result=added"
    ) in caplog.text


@pytest.mark.asyncio
async def test_admin_remove_writes_not_found_result(monkeypatch, caplog):
    actor_id = config.SUPERVISOR_ID
    target_id = 123456789

    async def remove_admin(user_id):
        assert user_id == target_id
        return False

    monkeypatch.setattr(admin_handler.db, "remove_admin", remove_admin)
    message = FakeMessage(actor_id)
    command = SimpleNamespace(args=str(target_id))

    with caplog.at_level(logging.INFO, logger="bot.audit"):
        await admin_handler.cmd_admin_remove(message, command)

    assert (
        f"AUDIT action=admin_remove actor={actor_id} "
        f"target={target_id} result=not_found"
    ) in caplog.text


@pytest.mark.asyncio
async def test_non_supervisor_admin_command_is_audited(monkeypatch, caplog):
    message = FakeMessage(config.SUPERVISOR_ID - 1)

    with caplog.at_level(logging.INFO, logger="bot.audit"):
        await admin_handler.cmd_admin(message)

    assert (
        f"AUDIT action=admin_denied actor={config.SUPERVISOR_ID - 1} "
        "target=None result=denied"
    ) in caplog.text
    assert message.answers == ["⛔ Доступ запрещён."]


@pytest.mark.asyncio
async def test_history_limit_for_another_user_is_audited(monkeypatch, caplog):
    actor_id = config.SUPERVISOR_ID
    target_id = 123456789
    exchange_limit = 35
    calls = []

    async def set_history_limit(user_id, limit):
        calls.append((user_id, limit))

    async def send_prompt_status(message, state, text):
        return None

    monkeypatch.setattr(
        history_limits_handler.db, "set_history_limit", set_history_limit
    )
    monkeypatch.setattr(
        history_limits_handler,
        "send_prompt_status",
        send_prompt_status,
    )
    message = FakeMessage(actor_id)
    state = SimpleNamespace()
    command = SimpleNamespace(args=f"{target_id} {exchange_limit}")

    with caplog.at_level(logging.INFO, logger="bot.audit"):
        await history_limits_handler.cmd_history_limit(message, state, command)

    assert calls == [(target_id, exchange_limit)]
    assert (
        f"AUDIT action=history_limit_set actor={actor_id} "
        f"target={target_id} result={exchange_limit}"
    ) in caplog.text


@pytest.mark.asyncio
async def test_ban_command_blocks_non_admin_and_audits(monkeypatch, caplog):
    actor_id = config.SUPERVISOR_ID
    target_id = 123456789
    calls = []

    async def get_admin_ids():
        return set()

    async def block_user(user_id):
        calls.append(user_id)
        return True

    monkeypatch.setattr(admin_handler.db, "get_admin_ids", get_admin_ids)
    monkeypatch.setattr(admin_handler.db, "block_user", block_user)
    message = FakeMessage(actor_id)
    command = SimpleNamespace(args=str(target_id))

    with caplog.at_level(logging.INFO, logger="bot.audit"):
        await admin_handler.cmd_ban(message, command)

    assert calls == [target_id]
    assert message.answers == [f"✅ Пользователь {target_id} заблокирован."]
    assert (
        f"AUDIT action=ban actor={actor_id} target={target_id} result=blocked"
    ) in caplog.text


@pytest.mark.asyncio
async def test_ban_rejects_supervisor_and_admin_targets(monkeypatch):
    actor_id = config.SUPERVISOR_ID
    admin_id = 123456789

    async def get_admin_ids():
        return {admin_id}

    monkeypatch.setattr(admin_handler.db, "get_admin_ids", get_admin_ids)

    # Verify that a protected target never reaches the database.
    async def forbidden_block(user_id):
        pytest.fail("Нельзя вызывать block_user для защищённой цели")

    monkeypatch.setattr(admin_handler.db, "block_user", forbidden_block)

    for target_id in (actor_id, admin_id):
        message = FakeMessage(actor_id)
        await admin_handler.cmd_ban(message, SimpleNamespace(args=str(target_id)))
        assert "заблокировать нельзя" in message.answers[0]


@pytest.mark.asyncio
async def test_unban_command_removes_block_and_audits(monkeypatch, caplog):
    actor_id = config.SUPERVISOR_ID
    target_id = 123456789

    async def get_admin_ids():
        return set()

    async def unblock_user(user_id):
        assert user_id == target_id
        return True

    monkeypatch.setattr(admin_handler.db, "get_admin_ids", get_admin_ids)
    monkeypatch.setattr(admin_handler.db, "unblock_user", unblock_user)
    message = FakeMessage(actor_id)

    with caplog.at_level(logging.INFO, logger="bot.audit"):
        await admin_handler.cmd_unban(message, SimpleNamespace(args=str(target_id)))

    assert message.answers == [f"✅ Блокировка пользователя {target_id} снята."]
    assert (
        f"AUDIT action=unban actor={actor_id} target={target_id} result=unblocked"
    ) in caplog.text


@pytest.mark.asyncio
async def test_database_admin_can_ban_non_admin(monkeypatch, caplog):
    actor_id = config.SUPERVISOR_ID - 10
    target_id = 123456789
    blocked = []

    async def get_admin_ids():
        return {actor_id}

    async def block_user(user_id):
        blocked.append(user_id)
        return True

    monkeypatch.setattr(admin_handler.db, "get_admin_ids", get_admin_ids)
    monkeypatch.setattr(admin_handler.db, "block_user", block_user)
    message = FakeMessage(actor_id)

    with caplog.at_level(logging.INFO, logger="bot.audit"):
        await admin_handler.cmd_ban(message, SimpleNamespace(args=str(target_id)))

    assert blocked == [target_id]
    assert message.answers == [f"✅ Пользователь {target_id} заблокирован."]
    assert f"AUDIT action=ban actor={actor_id}" in caplog.text


@pytest.mark.asyncio
async def test_non_admin_cannot_ban(monkeypatch, caplog):
    actor_id = config.SUPERVISOR_ID - 10
    target_id = 123456789

    async def get_admin_ids():
        return set()

    async def forbidden_block_user(user_id):
        pytest.fail("Пользователь без прав не должен блокировать аккаунты")

    monkeypatch.setattr(admin_handler.db, "get_admin_ids", get_admin_ids)
    monkeypatch.setattr(admin_handler.db, "block_user", forbidden_block_user)
    message = FakeMessage(actor_id)

    with caplog.at_level(logging.INFO, logger="bot.audit"):
        await admin_handler.cmd_ban(message, SimpleNamespace(args=str(target_id)))

    assert message.answers == ["⛔ Доступ запрещён."]
    assert (
        f"AUDIT action=admin_denied actor={actor_id} target=None result=denied"
    ) in caplog.text
