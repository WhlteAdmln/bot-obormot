# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""In-process end-to-end chat flows."""

import base64
from functools import partial
from io import BytesIO

import pytest
from aiogram.methods import EditMessageText, GetFile, SendChatAction, SendMessage
from aiogram.types import File as TelegramFile
from aiogram.types import PhotoSize
from PIL import Image

import bot_obormot.app.routers as app_routers
from bot_obormot.middlewares import throttle as throttle_middleware
from bot_obormot.services.chat.streaming.settings import MAX_MESSAGE_LENGTH
from bot_obormot.services.database import Database
from bot_obormot.settings import Settings
from tests.support.chat_flows import (
    configure_document_flow,
    configure_llm_flow,
    configure_voice_flow,
    make_document_message,
    make_document_telegram_session,
    make_private_message,
    make_voice_message,
    make_voice_telegram_session,
    open_flow,
)
from tests.support.fake_audiodoc import FakeAudiodoc
from tests.support.fake_llm import FakeLLM, FakeLLMOptions
from tests.support.telegram import FakeTelegramSession, make_message, make_update


def _assert_voice_delivery(
    telegram_session: FakeTelegramSession,
    llm_server: FakeLLM,
    response: str,
) -> None:
    """Verify Telegram download and streamed response delivery."""
    file_requests = [
        request for request in telegram_session.requests if isinstance(request, GetFile)
    ]
    sent_messages = [
        request
        for request in telegram_session.requests
        if isinstance(request, SendMessage)
    ]
    edited_texts = [
        request.text
        for request in telegram_session.requests
        if isinstance(request, EditMessageText) and request.text is not None
    ]

    assert len(file_requests) == 1
    assert telegram_session.streamed_urls
    assert telegram_session.streamed_urls[0].endswith("/voice/test.ogg")
    assert llm_server.stream_started.is_set()
    assert len(sent_messages) == 1
    assert edited_texts
    assert edited_texts[-1] == response


async def _assert_voice_history(
    test_db: Database,
    user_id: int,
    response: str,
) -> None:
    """Verify that transcription and assistant response were persisted."""
    history = await test_db.get_history(user_id)

    expected_count = 2
    assert len(history) == expected_count
    expected_fragment = "Recognized speech."
    assert expected_fragment in history[0]["content"]
    assert history[1]["content"] == response


@pytest.mark.asyncio
async def test_text_message_streams_answer_and_persists_exchange(
    test_db: Database,
) -> None:
    """Process a text message through Dispatcher, LLM and SQLite."""
    user_id = 712345678
    user_text = "Объясни, пожалуйста, как работает SQLite."
    first_chunk = " ".join(["streamed"] * 180) + " "
    response = f"{first_chunk}complete"
    async with FakeLLM(
        options=FakeLLMOptions(chunks=(first_chunk, "complete")),
    ) as llm_server:
        settings = configure_llm_flow(llm_server.base_url)

        telegram_session = FakeTelegramSession(
            {
                SendChatAction: True,
                SendMessage: make_message(
                    message_id=900,
                    chat_id=user_id,
                    user_id=900,
                    text=None,
                ),
                EditMessageText: make_message(
                    message_id=900,
                    chat_id=user_id,
                    user_id=900,
                    text=None,
                ),
            }
        )
        async with open_flow(settings, test_db, telegram_session) as (bot, dispatcher):
            await dispatcher.feed_update(
                bot,
                make_update(
                    message=make_message(
                        user_id=user_id,
                        chat_id=user_id,
                        text=user_text,
                    )
                ),
            )

        sent_messages = [
            request
            for request in telegram_session.requests
            if isinstance(request, SendMessage)
        ]
        edited_texts = [
            request.text
            for request in telegram_session.requests
            if isinstance(request, EditMessageText) and request.text is not None
        ]

        assert llm_server.stream_started.is_set()
        assert len(sent_messages) == 1
        assert sent_messages[0].text is not None
        expected_fragment = "streamed"
        assert expected_fragment in sent_messages[0].text
        assert edited_texts
        assert edited_texts[-1] == response

        history = await test_db.get_history(user_id)
        assert [(item["role"], item["content"]) for item in history] == [
            ("user", user_text),
            ("assistant", response),
        ]


@pytest.mark.asyncio
async def test_voice_message_is_transcribed_answered_and_persisted(
    test_db: Database,
) -> None:
    """Process a voice message through Telegram, audiodoc, LLM and SQLite."""
    user_id = 712345679
    first_chunk = " ".join(["streamed"] * 180) + " "
    response = f"{first_chunk}complete"
    audio_data = b"OggS-fake-voice-data"
    async with (
        FakeAudiodoc() as audiodoc_server,
        FakeLLM(
            options=FakeLLMOptions(chunks=(first_chunk, "complete")),
        ) as llm_server,
    ):
        settings = configure_voice_flow(
            llm_base_url=llm_server.base_url,
            audiodoc_base_url=audiodoc_server.base_url,
        )

        telegram_session = make_voice_telegram_session(user_id, audio_data)
        voice_message = make_voice_message(user_id, len(audio_data))
        async with open_flow(settings, test_db, telegram_session) as (bot, dispatcher):
            await dispatcher.feed_update(
                bot,
                make_update(message=voice_message),
            )

        _assert_voice_delivery(telegram_session, llm_server, response)
        await _assert_voice_history(test_db, user_id, response)


def _assert_document_delivery(
    telegram_session: FakeTelegramSession,
    llm_server: FakeLLM,
    response: str,
) -> None:
    file_requests = [
        request for request in telegram_session.requests if isinstance(request, GetFile)
    ]
    sent_messages = [
        request
        for request in telegram_session.requests
        if isinstance(request, SendMessage)
    ]
    edited_texts = [
        request.text
        for request in telegram_session.requests
        if isinstance(request, EditMessageText) and request.text is not None
    ]

    assert len(file_requests) == 1
    assert telegram_session.streamed_urls
    assert telegram_session.streamed_urls[0].endswith("/documents/report.pdf")
    assert llm_server.stream_started.is_set()
    assert len(sent_messages) == 1
    assert edited_texts
    assert edited_texts[-1] == response
    assert llm_server.chat_requests
    expected_fragment = "Example document text."
    assert any(
        expected_fragment in str(request.get("messages", []))
        for request in llm_server.chat_requests
    )


async def _assert_document_history(
    test_db: Database,
    user_id: int,
    response: str,
) -> None:
    history = await test_db.get_history(user_id)
    expected_count = 2
    assert len(history) == expected_count
    expected_content = "[Пользователь отправил документ: report.pdf (TXT)]"
    assert history[0]["content"] == expected_content
    assert history[1]["content"] == response


@pytest.mark.asyncio
async def test_pdf_document_is_extracted_answered_and_persisted(
    test_db: Database,
) -> None:
    """Process a PDF through Telegram, audiodoc, LLM and SQLite."""
    user_id = 712345680
    first_chunk = " ".join(["streamed"] * 180) + " "
    response = f"{first_chunk}complete"
    document_data = b"%PDF-1.7\n% fake PDF integration document\n"
    async with (
        FakeAudiodoc() as audiodoc_server,
        FakeLLM(
            options=FakeLLMOptions(chunks=(first_chunk, "complete")),
        ) as llm_server,
    ):
        settings = configure_document_flow(
            llm_base_url=llm_server.base_url,
            audiodoc_base_url=audiodoc_server.base_url,
        )

        telegram_session = make_document_telegram_session(
            user_id,
            document_data,
        )
        document_message = make_document_message(
            user_id,
            len(document_data),
        )
        async with open_flow(settings, test_db, telegram_session) as (bot, dispatcher):
            await dispatcher.feed_update(
                bot,
                make_update(message=document_message),
            )

        _assert_document_delivery(telegram_session, llm_server, response)
        await _assert_document_history(test_db, user_id, response)


def _assert_photo_delivery(
    telegram_session: FakeTelegramSession,
    llm_server: FakeLLM,
    response: str,
) -> None:
    """Verify photo download, Vision payload and streamed response delivery."""
    file_requests = [
        request for request in telegram_session.requests if isinstance(request, GetFile)
    ]
    sent_messages = [
        request
        for request in telegram_session.requests
        if isinstance(request, SendMessage)
    ]
    edited_texts = [
        request.text
        for request in telegram_session.requests
        if isinstance(request, EditMessageText) and request.text is not None
    ]

    assert len(file_requests) == 1
    assert telegram_session.streamed_urls
    assert telegram_session.streamed_urls[0].endswith("/photos/photo.png")
    assert llm_server.stream_started.is_set()
    assert len(sent_messages) == 1
    assert edited_texts
    assert edited_texts[-1] == response

    expected_get = "image_url"
    image_parts = [
        part
        for request in llm_server.chat_requests
        for llm_message in request.get("messages", [])
        for part in (
            llm_message.get("content", [])
            if isinstance(llm_message.get("content"), list)
            else []
        )
        if isinstance(part, dict) and part.get("type") == expected_get
    ]

    assert len(image_parts) == 1
    image_url = image_parts[0]["image_url"]["url"]
    assert image_url.startswith("data:image/jpeg;base64,")

    decoded_image = base64.b64decode(image_url.split(",", 1)[1])
    with Image.open(BytesIO(decoded_image)) as prepared_image:
        expected_format = "JPEG"
        assert prepared_image.format == expected_format
        assert prepared_image.size == (2, 2)


async def _assert_photo_history(
    test_db: Database,
    user_id: int,
    response: str,
) -> None:
    """Verify that the photo and assistant response were persisted."""
    history = await test_db.get_history(user_id)

    expected_count = 2
    assert len(history) == expected_count
    assert isinstance(history[0]["content"], list)
    expected_get = "image_url"
    assert any(
        isinstance(part, dict) and part.get("type") == expected_get
        for part in history[0]["content"]
    )
    assert history[1]["content"] == response


@pytest.mark.asyncio
async def test_photo_message_is_processed_by_vision_and_persisted(
    test_db: Database,
) -> None:
    """Process a photo through Telegram, Vision, LLM and SQLite."""
    user_id = 712345681
    first_chunk = " ".join(["streamed"] * 180) + " "
    response = f"{first_chunk}complete"

    image_buffer = BytesIO()
    Image.new("RGB", (2, 2), (24, 48, 96)).save(image_buffer, format="PNG")
    image_data = image_buffer.getvalue()

    async with FakeLLM(
        options=FakeLLMOptions(chunks=(first_chunk, "complete")),
    ) as llm_server:
        settings = configure_llm_flow(llm_server.base_url)

        telegram_session = FakeTelegramSession(
            {
                GetFile: TelegramFile(
                    file_id="photo-file-id",
                    file_unique_id="photo-file-unique-id",
                    file_size=len(image_data),
                    file_path="photos/photo.png",
                ),
                SendChatAction: True,
                SendMessage: make_message(
                    message_id=903,
                    chat_id=user_id,
                    user_id=903,
                    text=None,
                ),
                EditMessageText: make_message(
                    message_id=903,
                    chat_id=user_id,
                    user_id=903,
                    text=None,
                ),
            },
            stream_data=image_data,
        )
        photo_message = make_private_message(
            user_id,
            photo=[
                PhotoSize(
                    file_id="photo-file-id",
                    file_unique_id="photo-file-unique-id",
                    width=2,
                    height=2,
                    file_size=len(image_data),
                )
            ],
        )
        async with open_flow(settings, test_db, telegram_session) as (bot, dispatcher):
            await dispatcher.feed_update(
                bot,
                make_update(message=photo_message),
            )

        _assert_photo_delivery(telegram_session, llm_server, response)
        await _assert_photo_history(test_db, user_id, response)


@pytest.mark.asyncio
async def test_blocked_user_is_denied_before_llm_is_called(
    test_db: Database,
) -> None:
    """Reject a blocked user through Dispatcher without calling the LLM."""
    user_id = 712345682
    denied_text = "⛔ У тебя нет доступа к этому боту."

    assert await test_db.block_user(user_id) is True
    async with FakeLLM() as llm_server:
        settings = configure_llm_flow(
            llm_server.base_url,
            ALLOWED_USERS={user_id},
        )

        telegram_session = FakeTelegramSession(
            {
                SendMessage: make_message(
                    message_id=904,
                    chat_id=user_id,
                    user_id=904,
                    text=None,
                ),
            }
        )
        async with open_flow(settings, test_db, telegram_session) as (bot, dispatcher):
            await dispatcher.feed_update(
                bot,
                make_update(
                    message=make_message(
                        user_id=user_id,
                        chat_id=user_id,
                        text="This request must be rejected.",
                    )
                ),
            )

        sent_messages = [
            request
            for request in telegram_session.requests
            if isinstance(request, SendMessage)
        ]

        assert len(sent_messages) == 1
        assert sent_messages[0].text == denied_text
        assert len(telegram_session.requests) == 1
        assert llm_server.chat_requests == []
        assert not llm_server.stream_started.is_set()
        assert await test_db.get_history(user_id) == []


@pytest.mark.asyncio
async def test_throttled_user_is_blocked_before_llm_is_called(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject the eleventh message in a burst before calling the LLM."""
    user_id = 712345683
    allowed_questions = [f"Question {index}" for index in range(1, 11)]
    blocked_question = "Question 11"
    async with FakeLLM() as llm_server:
        settings = configure_llm_flow(llm_server.base_url)
        monkeypatch.setattr(
            app_routers,
            "ThrottleMiddleware",
            partial(
                throttle_middleware.ThrottleMiddleware,
                clock=lambda: 1.0,
            ),
        )

        telegram_session = FakeTelegramSession(
            {
                SendChatAction: True,
                SendMessage: make_message(
                    message_id=905,
                    chat_id=user_id,
                    user_id=905,
                    text=None,
                ),
                EditMessageText: make_message(
                    message_id=905,
                    chat_id=user_id,
                    user_id=905,
                    text=None,
                ),
            }
        )
        async with open_flow(settings, test_db, telegram_session) as (bot, dispatcher):
            for update_id, question in enumerate(
                (*allowed_questions, blocked_question),
                start=1,
            ):
                await dispatcher.feed_update(
                    bot,
                    make_update(
                        update_id=update_id,
                        message=make_message(
                            message_id=update_id,
                            user_id=user_id,
                            chat_id=user_id,
                            text=question,
                        ),
                    ),
                )

        sent_messages = [
            request
            for request in telegram_session.requests
            if isinstance(request, SendMessage)
        ]

        expected_count = 10
        assert len(sent_messages) == expected_count
        expected_count = 10
        assert len(llm_server.chat_requests) == expected_count
        assert llm_server.stream_started.is_set()

        history = await test_db.get_history(user_id)
        assert [(item["role"], item["content"]) for item in history] == [
            entry
            for question in allowed_questions
            for entry in (
                ("user", question),
                ("assistant", "Hello, world!"),
            )
        ]


@pytest.mark.asyncio
async def test_long_answer_is_split_into_multiple_telegram_messages(
    test_db: Database,
) -> None:
    """Split a long streamed answer into Telegram-sized messages and persist it."""
    user_id = 712345684
    user_text = "Напиши очень длинный ответ."
    response = " ".join(["long-answer"] * 1200)
    async with FakeLLM(
        options=FakeLLMOptions(chunks=(response,)),
    ) as llm_server:
        settings = configure_llm_flow(llm_server.base_url)

        telegram_session = FakeTelegramSession(
            {
                SendChatAction: True,
                SendMessage: make_message(
                    message_id=906,
                    chat_id=user_id,
                    user_id=906,
                    text=None,
                ),
                EditMessageText: make_message(
                    message_id=906,
                    chat_id=user_id,
                    user_id=906,
                    text=None,
                ),
            }
        )
        async with open_flow(settings, test_db, telegram_session) as (bot, dispatcher):
            await dispatcher.feed_update(
                bot,
                make_update(
                    message=make_message(
                        user_id=user_id,
                        chat_id=user_id,
                        text=user_text,
                    )
                ),
            )

        sent_messages = [
            request
            for request in telegram_session.requests
            if isinstance(request, SendMessage)
        ]
        delivered_chunks = [
            request.text for request in sent_messages if request.text is not None
        ]

        assert llm_server.stream_started.is_set()
        expected_count = 4
        assert len(sent_messages) == expected_count
        assert len(delivered_chunks) == len(sent_messages)
        assert all(len(chunk) <= MAX_MESSAGE_LENGTH for chunk in delivered_chunks)
        assert " ".join(delivered_chunks) == response

        history = await test_db.get_history(user_id)
        assert [(item["role"], item["content"]) for item in history] == [
            ("user", user_text),
            ("assistant", response),
        ]


@pytest.mark.asyncio
async def test_llm_connection_failure_is_reported_without_persisting_exchange(
    test_db: Database,
) -> None:
    """Report LLM connection loss and leave the conversation history unchanged."""
    user_id = 712345685
    error_prefix = "🔌 Не удалось связаться с языковой моделью."
    error_suffix = "Проверь доступность AI-сервера."
    expected_error = f"{error_prefix} {error_suffix}"
    async with FakeLLM() as llm_server:
        settings_overrides = {
            "LLM_CONTEXT_SIZE": 8192,
            "LLM_TOKEN_COUNTING": "estimate",
        }
        settings = configure_llm_flow(
            llm_server.base_url,
            **settings_overrides,
        )

        await llm_server.server.close()

        telegram_session = FakeTelegramSession(
            {
                SendChatAction: True,
                SendMessage: make_message(
                    message_id=907,
                    chat_id=user_id,
                    user_id=907,
                    text=None,
                ),
            }
        )
        async with open_flow(settings, test_db, telegram_session) as (bot, dispatcher):
            await dispatcher.feed_update(
                bot,
                make_update(
                    message=make_message(
                        user_id=user_id,
                        chat_id=user_id,
                        text="This request must fail because the LLM is offline.",
                    )
                ),
            )

        sent_messages = [
            request
            for request in telegram_session.requests
            if isinstance(request, SendMessage)
        ]

        assert len(sent_messages) == 1
        assert sent_messages[0].text == expected_error
        assert llm_server.chat_requests == []
        assert not llm_server.stream_started.is_set()
        assert not any(
            isinstance(request, EditMessageText)
            for request in telegram_session.requests
        )
        assert await test_db.get_history(user_id) == []


@pytest.mark.asyncio
async def test_document_connection_failure_is_reported_without_persisting_exchange(
    test_db: Database,
) -> None:
    """Report audiodoc connection loss without persisting the exchange."""
    user_id = 712345686
    expected_error = "🔌 Не удалось связаться с сервисом обработки документов."
    document_data = b"%PDF-1.7\n% unavailable audiodoc integration document\n"
    async with (
        FakeAudiodoc() as audiodoc_server,
        FakeLLM() as llm_server,
    ):
        settings = configure_document_flow(
            llm_base_url=llm_server.base_url,
            audiodoc_base_url=audiodoc_server.base_url,
        )
        await audiodoc_server.server.close()

        telegram_session = make_document_telegram_session(
            user_id,
            document_data,
        )
        async with open_flow(settings, test_db, telegram_session) as (bot, dispatcher):
            await dispatcher.feed_update(
                bot,
                make_update(
                    message=make_document_message(
                        user_id,
                        len(document_data),
                    ),
                ),
            )

        sent_messages = [
            request
            for request in telegram_session.requests
            if isinstance(request, SendMessage)
        ]
        file_requests = [
            request
            for request in telegram_session.requests
            if isinstance(request, GetFile)
        ]

        assert len(file_requests) == 1
        assert telegram_session.streamed_urls
        assert telegram_session.streamed_urls[0].endswith("/documents/report.pdf")
        assert len(sent_messages) == 1
        assert sent_messages[0].text == expected_error
        assert llm_server.chat_requests == []
        assert not llm_server.stream_started.is_set()
        assert not any(
            isinstance(request, EditMessageText)
            for request in telegram_session.requests
        )
        assert await test_db.get_history(user_id) == []


def _configure_history_limit_flow(llm_server: FakeLLM) -> Settings:
    """Configure the application to use the fake LLM."""
    return configure_llm_flow(llm_server.base_url)


async def _dispatch_history_limit_message(
    test_db: Database,
    user_id: int,
    user_text: str,
    settings: Settings,
) -> FakeTelegramSession:
    """Process a text message through the real application dispatcher."""
    telegram_session = FakeTelegramSession(
        {
            SendChatAction: True,
            SendMessage: make_message(
                message_id=909,
                chat_id=user_id,
                user_id=909,
                text=None,
            ),
            EditMessageText: make_message(
                message_id=909,
                chat_id=user_id,
                user_id=909,
                text=None,
            ),
        }
    )
    async with open_flow(settings, test_db, telegram_session) as (bot, dispatcher):
        await dispatcher.feed_update(
            bot,
            make_update(
                message=make_message(
                    user_id=user_id,
                    chat_id=user_id,
                    text=user_text,
                )
            ),
        )

    return telegram_session


def _assert_history_limit_context(
    llm_server: FakeLLM,
    previous_exchanges: list[tuple[str, str]],
    user_text: str,
) -> None:
    """Verify that only the latest previous exchange reaches the LLM."""
    assert llm_server.stream_started.is_set()
    assert len(llm_server.chat_requests) == 1

    request_messages = llm_server.chat_requests[0]["messages"]
    assert isinstance(request_messages, list)
    context_text = str(request_messages)

    for question, answer in previous_exchanges[:-1]:
        assert question not in context_text
        assert answer not in context_text

    assert previous_exchanges[-1][0] in context_text
    assert previous_exchanges[-1][1] in context_text
    assert user_text in context_text


def _assert_history_limit_delivery(
    telegram_session: FakeTelegramSession,
    response: str,
) -> None:
    """Verify that Telegram receives the completed answer."""
    sent_messages = [
        request
        for request in telegram_session.requests
        if isinstance(request, SendMessage)
    ]
    edited_texts = [
        request.text
        for request in telegram_session.requests
        if isinstance(request, EditMessageText) and request.text is not None
    ]

    assert len(sent_messages) == 1
    delivered_text = sent_messages[0].text
    if edited_texts:
        delivered_text = edited_texts[-1]
    assert delivered_text == response


async def _assert_history_limit_persistence(
    test_db: Database,
    user_id: int,
    previous_exchanges: list[tuple[str, str]],
    user_text: str,
    response: str,
) -> None:
    """Verify that the complete conversation remains stored in SQLite."""
    history = await test_db.get_history(user_id)
    expected_exchanges = [*previous_exchanges, (user_text, response)]
    expected_history = [
        (role, content)
        for question, answer in expected_exchanges
        for role, content in (
            ("user", question),
            ("assistant", answer),
        )
    ]

    assert [(item["role"], item["content"]) for item in history] == expected_history


@pytest.mark.asyncio
async def test_history_limit_restricts_llm_context_and_preserves_history(
    test_db: Database,
) -> None:
    """Limit the LLM context without deleting older stored exchanges."""
    user_id = 712345687
    previous_exchanges = [
        ("Previous question 1", "Previous answer 1"),
        ("Previous question 2", "Previous answer 2"),
        ("Previous question 3", "Previous answer 3"),
    ]

    for question, answer in previous_exchanges:
        await test_db.add_exchange(user_id, question, answer)
    await test_db.set_history_limit(user_id, 1)

    user_text = "Use only the recent conversation."
    response = "History limit respected."

    async with FakeLLM(
        options=FakeLLMOptions(chunks=(response,)),
    ) as llm_server:
        settings = _configure_history_limit_flow(llm_server)
        telegram_session = await _dispatch_history_limit_message(
            test_db,
            user_id,
            user_text,
            settings,
        )
        _assert_history_limit_context(
            llm_server,
            previous_exchanges,
            user_text,
        )
        _assert_history_limit_delivery(telegram_session, response)
        await _assert_history_limit_persistence(
            test_db,
            user_id,
            previous_exchanges,
            user_text,
            response,
        )
