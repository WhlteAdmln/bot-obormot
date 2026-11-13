# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""SQL-запросы для чтения истории диалогов."""

HISTORY_WITH_MEDIA = """
    WITH ordered_messages AS (
        SELECT
            id,
            user_id,
            role,
            LEAD(id) OVER (
                PARTITION BY user_id
                ORDER BY id
            ) AS next_id,
            LEAD(role) OVER (
                PARTITION BY user_id
                ORDER BY id
            ) AS next_role
        FROM messages
        WHERE user_id = ?
    ),
    recent_exchanges AS (
        SELECT
            id AS user_message_id,
            next_id AS assistant_message_id
        FROM ordered_messages
        WHERE role = 'user'
          AND next_role = 'assistant'
        ORDER BY id DESC
        LIMIT ?
    ),
    selected_messages AS (
        SELECT user_message_id AS message_id
        FROM recent_exchanges

        UNION ALL

        SELECT assistant_message_id AS message_id
        FROM recent_exchanges
    ),
    recent_media_messages AS (
        SELECT
            mm.message_id,
            MAX(mm.id) AS latest_media_id
        FROM message_media AS mm
        JOIN selected_messages AS sm
            ON sm.message_id = mm.message_id
        GROUP BY mm.message_id
        ORDER BY latest_media_id DESC
        LIMIT ?
    ),
    recent_media AS (
        SELECT
            mm.id,
            mm.message_id,
            mm.file_path,
            mm.mime_type
        FROM message_media AS mm
        JOIN recent_media_messages AS rmm
            ON rmm.message_id = mm.message_id
    )
    SELECT
        m.id,
        m.role,
        m.content,
        rm.file_path,
        rm.mime_type
    FROM selected_messages AS sm
    JOIN messages AS m
        ON m.id = sm.message_id
    LEFT JOIN recent_media AS rm
        ON rm.message_id = m.id
    ORDER BY m.id ASC, rm.id ASC
"""
