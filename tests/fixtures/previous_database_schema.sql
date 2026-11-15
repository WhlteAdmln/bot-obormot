-- SQLite schema from revision 538c4d0, before blocked_users was added.

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_user_id_id ON messages(user_id, id);

CREATE TABLE user_settings (
    user_id INTEGER PRIMARY KEY,
    system_prompt TEXT NOT NULL
);

CREATE TABLE user_history_limits (
    user_id INTEGER PRIMARY KEY,
    exchange_limit INTEGER NOT NULL CHECK(exchange_limit >= 1)
);

CREATE TABLE admins (
    user_id INTEGER PRIMARY KEY,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE app_migrations (
    name TEXT PRIMARY KEY,
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE message_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    mime_type TEXT NOT NULL DEFAULT 'image/jpeg',
    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
);

CREATE INDEX idx_message_media_message_id ON message_media(message_id);

INSERT INTO messages(id, user_id, role, content, created_at)
VALUES (1, 424242, 'user', 'Legacy message', '2025-01-01 00:00:00');

INSERT INTO user_settings(user_id, system_prompt)
VALUES (424242, 'Legacy prompt');

INSERT INTO user_history_limits(user_id, exchange_limit)
VALUES (424242, 7);

INSERT INTO admins(user_id) VALUES (101);

INSERT INTO message_media(message_id, file_path, mime_type)
VALUES (1, '/legacy/images/legacy.jpg', 'image/jpeg');
