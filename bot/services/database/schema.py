"""Создание таблиц и индексов SQLite."""

import aiosqlite


async def create_schema(connection: aiosqlite.Connection) -> None:
    """Создаёт структуру БД, если она ещё не существует."""

    await connection.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_user_id_id
        ON messages(user_id, id)
    """)

    await connection.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            system_prompt TEXT NOT NULL
        )
    """)

    await connection.execute("""
        CREATE TABLE IF NOT EXISTS user_history_limits (
            user_id INTEGER PRIMARY KEY,
            exchange_limit INTEGER NOT NULL
                CHECK(exchange_limit >= 1)
        )
    """)

    # Обычные администраторы.
    # Supervisor в этой таблице не хранится.
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # История выполненных миграций.
    await connection.execute("""
        CREATE TABLE IF NOT EXISTS app_migrations (
            name TEXT PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await connection.execute("""
        CREATE TABLE IF NOT EXISTS message_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            mime_type TEXT NOT NULL DEFAULT 'image/jpeg',
            FOREIGN KEY(message_id)
                REFERENCES messages(id) ON DELETE CASCADE
        )
    """)

    await connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_message_media_message_id
        ON message_media(message_id)
    """)

    await connection.execute("""
        CREATE TABLE IF NOT EXISTS blocked_users (
            user_id INTEGER PRIMARY KEY,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
