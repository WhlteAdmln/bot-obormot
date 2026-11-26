# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""In-process end-to-end chat flows."""

import base64
from collections.abc import Awaitable, Callable
from functools import partial
from io import BytesIO
from typing import Any, TypeVar

import pytest
from aiogram.methods import (
    EditMessageText,
    GetFile,
    SendChatAction,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import File as TelegramFile
from aiogram.types import Message, PhotoSize
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
from tests.support.fake_llm import FakeChatOptions, FakeLLM, FakeLLMOptions
from tests.support.telegram import FakeTelegramSession, make_message, make_update

FlowRun = tuple[FakeTelegramSession, FakeLLM]
_Method = TypeVar("_Method")
MediaFlow = Callable[[Database, int, tuple[str, ...]], Awaitable[FlowRun]]


def _streamed_chunks(word: str) -> tuple[str, ...]:
    return (" ".join([word] * 180) + " ", "complete")


def _requests_of(session: FakeTelegramSession, kind: type[_Method]) -> list[_Method]:
    return [request for request in session.requests if isinstance(request, kind)]


def _sent_messages(session: FakeTelegramSession) -> list[SendMessage]:
    return _requests_of(session, SendMessage)


def _edited_texts(session: FakeTelegramSession) -> list[str]:
    edits = _requests_of(session, EditMessageText)
    return [request.text for request in edits if request.text is not None]


def _image_parts(llm_server: FakeLLM) -> list[dict[str, Any]]:
    image_type = "image_url"
    return [
        part
        for request in llm_server.chat_requests
        for llm_message in request.get("messages", [])
        for part in (
            llm_message.get("content", [])
            if isinstance(llm_message.get("content"), list)
            else []
        )
        if isinstance(part, dict) and part.get("type") == image_type
    ]


def _decoded_image(llm_server: FakeLLM) -> bytes:
    image_url = str(_image_parts(llm_server)[0]["image_url"]["url"])
    return base64.b64decode(image_url.split(",", 1)[1])


async def _history_pairs(test_db: Database, user_id: int) -> list[tuple[str, Any]]:
    history = await test_db.get_history(user_id)
    return [(item["role"], item["content"]) for item in history]


def _streaming_responses(
    user_id: int, message_id: int
) -> dict[type[TelegramMethod[Any]], Any]:
    answer = make_message(
        message_id=message_id, chat_id=user_id, user_id=message_id, text=None
    )
    return {SendChatAction: True, SendMessage: answer, EditMessageText: answer}


def _streaming_session(user_id: int, message_id: int) -> FakeTelegramSession:
    return FakeTelegramSession(_streaming_responses(user_id, message_id))


async def _feed_text(
    settings: Settings,
    test_db: Database,
    telegram_session: FakeTelegramSession,
    user_id: int,
    text: str,
) -> None:
    async with open_flow(settings, test_db, telegram_session) as (bot, dispatcher):
        await dispatcher.feed_update(
            bot,
            make_update(
                message=make_message(
                    user_id=user_id,
                    chat_id=user_id,
                    text=text,
                )
            ),
        )


async def _run_text_flow(
    test_db: Database,
    user_id: int,
    chunks: tuple[str, ...],
    user_text: str,
) -> FlowRun:
    async with FakeLLM(
        options=FakeLLMOptions(chat=FakeChatOptions(chunks=chunks)),
    ) as llm_server:
        settings = configure_llm_flow(llm_server.base_url)
        telegram_session = _streaming_session(user_id, 900)
        await _feed_text(settings, test_db, telegram_session, user_id, user_text)
    return telegram_session, llm_server


async def _run_audiodoc_flow(
    test_db: Database,
    chunks: tuple[str, ...],
    configure: Callable[..., Settings],
    telegram_session: FakeTelegramSession,
    message: Message,
) -> FlowRun:
    async with (
        FakeAudiodoc() as audiodoc_server,
        FakeLLM(
            options=FakeLLMOptions(chat=FakeChatOptions(chunks=chunks)),
        ) as llm_server,
    ):
        settings = configure(
            llm_base_url=llm_server.base_url,
            audiodoc_base_url=audiodoc_server.base_url,
        )
        async with open_flow(settings, test_db, telegram_session) as (bot, dispatcher):
            await dispatcher.feed_update(bot, make_update(message=message))
    return telegram_session, llm_server


async def _run_voice_flow(
    test_db: Database, user_id: int, chunks: tuple[str, ...]
) -> FlowRun:
    audio_data = b"OggS-fake-voice-data"
    return await _run_audiodoc_flow(
        test_db,
        chunks,
        configure_voice_flow,
        make_voice_telegram_session(user_id, audio_data),
        make_voice_message(user_id, len(audio_data)),
    )


async def _run_document_flow(
    test_db: Database, user_id: int, chunks: tuple[str, ...]
) -> FlowRun:
    document_data = b"%PDF-1.7\n% fake PDF integration document\n"
    return await _run_audiodoc_flow(
        test_db,
        chunks,
        configure_document_flow,
        make_document_telegram_session(user_id, document_data),
        make_document_message(user_id, len(document_data)),
    )


async def _run_photo_flow(
    test_db: Database,
    user_id: int,
    chunks: tuple[str, ...],
) -> FlowRun:
    image_buffer = BytesIO()
    Image.new("RGB", (2, 2), (24, 48, 96)).save(image_buffer, format="PNG")
    image_data = image_buffer.getvalue()
    async with FakeLLM(
        options=FakeLLMOptions(chat=FakeChatOptions(chunks=chunks)),
    ) as llm_server:
        settings = configure_llm_flow(llm_server.base_url)
        photo_file = TelegramFile(
            file_id="photo-file-id",
            file_unique_id="photo-file-unique-id",
            file_size=len(image_data),
            file_path="photos/photo.png",
        )
        telegram_session = FakeTelegramSession(
            {**_streaming_responses(user_id, 903), GetFile: photo_file},
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
            await dispatcher.feed_update(bot, make_update(message=photo_message))
    return telegram_session, llm_server


async def _run_blocked_flow(test_db: Database, user_id: int) -> FlowRun:
    await test_db.block_user(user_id)
    text = "This request must be rejected."
    async with FakeLLM() as llm_server:
        settings = configure_llm_flow(llm_server.base_url, ALLOWED_USERS={user_id})
        answer = make_message(message_id=904, chat_id=user_id, user_id=904, text=None)
        telegram_session = FakeTelegramSession({SendMessage: answer})
        await _feed_text(settings, test_db, telegram_session, user_id, text)
    return telegram_session, llm_server


async def _run_throttled_flow(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
    user_id: int,
    questions: list[str],
) -> FlowRun:
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
        telegram_session = _streaming_session(user_id, 905)
        async with open_flow(settings, test_db, telegram_session) as (bot, dispatcher):
            for update_id, question in enumerate(questions, start=1):
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
    return telegram_session, llm_server


async def _run_llm_failure_flow(test_db: Database, user_id: int) -> FlowRun:
    text = "This request must fail because the LLM is offline."
    async with FakeLLM() as llm_server:
        overrides = {"LLM_CONTEXT_SIZE": 8192, "LLM_TOKEN_COUNTING": "estimate"}
        settings = configure_llm_flow(llm_server.base_url, **overrides)
        await llm_server.server.close()
        answer = make_message(message_id=907, chat_id=user_id, user_id=907, text=None)
        telegram_session = FakeTelegramSession(
            {SendChatAction: True, SendMessage: answer}
        )
        await _feed_text(settings, test_db, telegram_session, user_id, text)
    return telegram_session, llm_server


async def _run_document_failure_flow(test_db: Database, user_id: int) -> FlowRun:
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
        telegram_session = make_document_telegram_session(user_id, document_data)
        async with open_flow(settings, test_db, telegram_session) as (bot, dispatcher):
            await dispatcher.feed_update(
                bot,
                make_update(
                    message=make_document_message(user_id, len(document_data)),
                ),
            )
    return telegram_session, llm_server


async def _run_history_limit_flow(
    test_db: Database,
    user_id: int,
    previous_exchanges: list[tuple[str, str]],
    user_text: str,
    response: str,
) -> FlowRun:
    for question, answer in previous_exchanges:
        await test_db.add_exchange(user_id, question, answer)
    await test_db.set_history_limit(user_id, 1)
    async with FakeLLM(
        options=FakeLLMOptions(chat=FakeChatOptions(chunks=(response,))),
    ) as llm_server:
        settings = configure_llm_flow(llm_server.base_url)
        telegram_session = _streaming_session(user_id, 909)
        await _feed_text(settings, test_db, telegram_session, user_id, user_text)
    return telegram_session, llm_server


def _previous_exchanges(count: int) -> list[tuple[str, str]]:
    numbers = range(1, count + 1)
    return [(f"Previous question {n}", f"Previous answer {n}") for n in numbers]


def _context_text(llm_server: FakeLLM) -> str:
    return str(llm_server.chat_requests[0]["messages"])


_ANSWERED_FLOWS = pytest.mark.parametrize(
    "run_flow",
    [
        partial(_run_text_flow, user_text="Объясни, пожалуйста, как работает SQLite."),
        _run_voice_flow,
        _run_document_flow,
        _run_photo_flow,
    ],
    ids=["text", "voice", "document", "photo"],
)


@pytest.mark.asyncio
async def test_text_message_sends_a_text_message(test_db: Database) -> None:
    user_id = 712345602
    chunks = _streamed_chunks("partial")
    session, _llm = await _run_text_flow(test_db, user_id, chunks, "Что такое WAL?")
    sent_text = _sent_messages(session)[0].text
    assert sent_text is not None, "the first answer message has no text"


@pytest.mark.asyncio
async def test_text_message_sends_the_first_chunk_before_the_end(
    test_db: Database,
) -> None:
    user_id = 712345603
    streamed_word = "streamed"
    chunks = _streamed_chunks(streamed_word)
    user_text = "Как работает VACUUM?"
    session, _llm = await _run_text_flow(test_db, user_id, chunks, user_text)
    sent_text = _sent_messages(session)[0].text or ""
    assert streamed_word in sent_text, "the first chunk was not sent while streaming"


@pytest.mark.asyncio
async def test_text_message_persists_the_exchange(test_db: Database) -> None:
    user_id = 712345606
    user_text = "Объясни, пожалуйста, как работает SQLite."
    chunks = _streamed_chunks("stored")
    response = "".join(chunks)
    await _run_text_flow(test_db, user_id, chunks, user_text)
    expected = [("user", user_text), ("assistant", response)]
    history = await _history_pairs(test_db, user_id)
    assert history == expected, "the exchange was not stored"


_DOWNLOAD_FLOWS = [
    partial(_run_voice_flow, chunks=_streamed_chunks("voice")),
    partial(_run_document_flow, chunks=_streamed_chunks("document")),
    partial(_run_photo_flow, chunks=_streamed_chunks("photo")),
    _run_document_failure_flow,
]
_DOWNLOAD_IDS = ["voice", "document", "photo", "document-service-offline"]


@pytest.mark.parametrize("run_flow", _DOWNLOAD_FLOWS, ids=_DOWNLOAD_IDS)
@pytest.mark.asyncio
async def test_file_message_looks_up_one_telegram_file(
    test_db: Database,
    run_flow: Callable[[Database, int], Awaitable[FlowRun]],
) -> None:
    user_id = 712345679
    session, _llm = await run_flow(test_db, user_id)
    expected_count = 1
    assert len(_requests_of(session, GetFile)) == expected_count, (
        "the file was not looked up"
    )


@pytest.mark.parametrize("run_flow", _DOWNLOAD_FLOWS, ids=_DOWNLOAD_IDS)
@pytest.mark.asyncio
async def test_file_message_downloads_the_file(
    test_db: Database,
    run_flow: Callable[[Database, int], Awaitable[FlowRun]],
) -> None:
    user_id = 712345611
    session, _llm = await run_flow(test_db, user_id)
    expected_empty: list[str] = []
    assert session.streamed_urls != expected_empty, "the file was not downloaded"


@pytest.mark.parametrize(
    ("run_flow", "file_path"),
    list(
        zip(
            _DOWNLOAD_FLOWS,
            [
                "/voice/test.ogg",
                "/documents/report.pdf",
                "/photos/photo.png",
                "/documents/report.pdf",
            ],
            strict=True,
        )
    ),
    ids=_DOWNLOAD_IDS,
)
@pytest.mark.asyncio
async def test_file_message_downloads_the_telegram_file_path(
    test_db: Database,
    run_flow: Callable[[Database, int], Awaitable[FlowRun]],
    file_path: str,
) -> None:
    user_id = 712345612
    session, _llm = await run_flow(test_db, user_id)
    downloaded_url = session.streamed_urls[0]
    assert downloaded_url.endswith(file_path), "a wrong file was downloaded"


@_ANSWERED_FLOWS
@pytest.mark.asyncio
async def test_answered_message_starts_the_llm_stream(
    test_db: Database,
    run_flow: MediaFlow,
) -> None:
    user_id = 712345613
    _session, llm_server = await run_flow(test_db, user_id, _streamed_chunks("start"))
    started = llm_server.stream_started.is_set()
    assert started is True, "the message did not reach the LLM"


@_ANSWERED_FLOWS
@pytest.mark.asyncio
async def test_answered_message_sends_one_telegram_message(
    test_db: Database,
    run_flow: MediaFlow,
) -> None:
    user_id = 712345614
    session, _llm = await run_flow(test_db, user_id, _streamed_chunks("single"))
    expected_count = 1
    assert len(_sent_messages(session)) == expected_count, (
        "the answer was not sent once"
    )


@_ANSWERED_FLOWS
@pytest.mark.asyncio
async def test_answered_message_edits_the_answer_while_streaming(
    test_db: Database,
    run_flow: MediaFlow,
) -> None:
    user_id = 712345615
    session, _llm = await run_flow(test_db, user_id, _streamed_chunks("editing"))
    expected_empty: list[str] = []
    assert _edited_texts(session) != expected_empty, "the answer was never edited"


@_ANSWERED_FLOWS
@pytest.mark.asyncio
async def test_answered_message_ends_with_the_complete_answer(
    test_db: Database,
    run_flow: MediaFlow,
) -> None:
    user_id = 712345616
    chunks = _streamed_chunks("whole")
    response = "".join(chunks)
    session, _llm = await run_flow(test_db, user_id, chunks)
    last_edit = _edited_texts(session)[-1]
    assert last_edit == response, "the last edit is not the complete answer"


@_ANSWERED_FLOWS
@pytest.mark.asyncio
async def test_answered_message_stores_two_history_entries(
    test_db: Database,
    run_flow: MediaFlow,
) -> None:
    user_id = 712345617
    await run_flow(test_db, user_id, _streamed_chunks("entries"))
    expected_count = 2
    history = await test_db.get_history(user_id)
    assert len(history) == expected_count, "the exchange was not stored as two entries"


@_ANSWERED_FLOWS
@pytest.mark.asyncio
async def test_answered_message_stores_the_complete_answer(
    test_db: Database,
    run_flow: MediaFlow,
) -> None:
    user_id = 712345618
    chunks = _streamed_chunks("persisted")
    response = "".join(chunks)
    await run_flow(test_db, user_id, chunks)
    history = await test_db.get_history(user_id)
    assert history[1]["content"] == response, "the stored answer is wrong"


@pytest.mark.asyncio
async def test_voice_message_stores_the_transcript(test_db: Database) -> None:
    user_id = 712345619
    transcript_text = "Recognized speech."
    await _run_voice_flow(test_db, user_id, _streamed_chunks("transcript"))
    history = await test_db.get_history(user_id)
    assert transcript_text in history[0]["content"], "the transcript was not stored"


@pytest.mark.asyncio
async def test_document_message_sends_the_document_text_to_the_llm(
    test_db: Database,
) -> None:
    user_id = 712345680
    _session, llm_server = await _run_document_flow(
        test_db, user_id, _streamed_chunks("context")
    )
    expected_empty: list[dict[str, Any]] = []
    assert llm_server.chat_requests != expected_empty, "the LLM received no request"


@pytest.mark.asyncio
async def test_document_message_includes_the_extracted_text_in_the_request(
    test_db: Database,
) -> None:
    user_id = 712345621
    document_text = "Example document text."
    _session, llm_server = await _run_document_flow(
        test_db, user_id, _streamed_chunks("extracted")
    )
    found = any(
        document_text in str(request.get("messages", []))
        for request in llm_server.chat_requests
    )
    assert found is True, "the extracted document text did not reach the LLM"


@pytest.mark.asyncio
async def test_document_message_stores_the_document_label(test_db: Database) -> None:
    user_id = 712345622
    expected_content = "[Пользователь отправил документ: report.pdf (TXT)]"
    await _run_document_flow(test_db, user_id, _streamed_chunks("label"))
    history = await test_db.get_history(user_id)
    assert history[0]["content"] == expected_content, "the document label is wrong"


@pytest.mark.asyncio
async def test_photo_message_sends_one_image_to_the_llm(test_db: Database) -> None:
    user_id = 712345681
    _session, llm_server = await _run_photo_flow(
        test_db, user_id, _streamed_chunks("vision")
    )
    expected_count = 1
    assert len(_image_parts(llm_server)) == expected_count, "not exactly one image"


@pytest.mark.asyncio
async def test_photo_message_sends_the_image_as_jpeg_data_url(
    test_db: Database,
) -> None:
    user_id = 712345623
    prefix = "data:image/jpeg;base64,"
    _session, llm_server = await _run_photo_flow(
        test_db, user_id, _streamed_chunks("dataurl")
    )
    image_url = str(_image_parts(llm_server)[0]["image_url"]["url"])
    assert image_url.startswith(prefix), "the image is not a JPEG data URL"


@pytest.mark.asyncio
async def test_photo_message_converts_the_image_to_jpeg(test_db: Database) -> None:
    user_id = 712345624
    expected_format = "JPEG"
    _session, llm_server = await _run_photo_flow(
        test_db, user_id, _streamed_chunks("format")
    )
    with Image.open(BytesIO(_decoded_image(llm_server))) as prepared_image:
        image_format = prepared_image.format
    assert image_format == expected_format, "the image was not converted to JPEG"


@pytest.mark.asyncio
async def test_photo_message_keeps_the_image_size(test_db: Database) -> None:
    user_id = 712345625
    expected_size = (2, 2)
    _session, llm_server = await _run_photo_flow(
        test_db, user_id, _streamed_chunks("size")
    )
    with Image.open(BytesIO(_decoded_image(llm_server))) as prepared_image:
        image_size = prepared_image.size
    assert image_size == expected_size, "the image size changed"


@pytest.mark.asyncio
async def test_photo_message_stores_the_question_as_parts(test_db: Database) -> None:
    user_id = 712345626
    await _run_photo_flow(test_db, user_id, _streamed_chunks("parts"))
    history = await test_db.get_history(user_id)
    content = history[0]["content"]
    assert isinstance(content, list), "the photo question is not stored as parts"


@pytest.mark.asyncio
async def test_photo_message_stores_the_image_part(test_db: Database) -> None:
    user_id = 712345627
    expected_type = "image_url"
    await _run_photo_flow(test_db, user_id, _streamed_chunks("image"))
    history = await test_db.get_history(user_id)
    found = any(
        isinstance(part, dict) and part.get("type") == expected_type
        for part in history[0]["content"]
    )
    assert found is True, "the stored photo question has no image part"


@pytest.mark.asyncio
async def test_block_user_reports_a_newly_blocked_user(test_db: Database) -> None:
    user_id = 712345682
    blocked = await test_db.block_user(user_id)
    assert blocked is True, "blocking a new user was not reported"


_REJECTED_FLOWS = [_run_blocked_flow, _run_llm_failure_flow, _run_document_failure_flow]
_REJECTED_IDS = ["blocked", "llm-offline", "document-service-offline"]


@pytest.mark.parametrize("run_flow", _REJECTED_FLOWS, ids=_REJECTED_IDS)
@pytest.mark.asyncio
async def test_rejected_message_gets_one_reply(
    test_db: Database,
    run_flow: Callable[[Database, int], Awaitable[FlowRun]],
) -> None:
    user_id = 712345631
    session, _llm = await run_flow(test_db, user_id)
    expected_count = 1
    assert len(_sent_messages(session)) == expected_count, "not exactly one reply"


@pytest.mark.parametrize(
    ("run_flow", "expected_text"),
    list(
        zip(
            _REJECTED_FLOWS,
            [
                "⛔ У тебя нет доступа к этому боту.",
                (
                    "🔌 Не удалось связаться с языковой моделью."
                    " Проверь доступность AI-сервера."
                ),
                "🔌 Не удалось связаться с сервисом обработки документов.",
            ],
            strict=True,
        )
    ),
    ids=_REJECTED_IDS,
)
@pytest.mark.asyncio
async def test_rejected_message_is_answered_with_the_reason(
    test_db: Database,
    run_flow: Callable[[Database, int], Awaitable[FlowRun]],
    expected_text: str,
) -> None:
    user_id = 712345632
    session, _llm = await run_flow(test_db, user_id)
    sent_text = _sent_messages(session)[0].text
    assert sent_text == expected_text, "the reply does not explain the rejection"


@pytest.mark.parametrize("run_flow", _REJECTED_FLOWS, ids=_REJECTED_IDS)
@pytest.mark.asyncio
async def test_rejected_message_sends_no_request_to_the_llm(
    test_db: Database,
    run_flow: Callable[[Database, int], Awaitable[FlowRun]],
) -> None:
    user_id = 712345634
    _session, llm_server = await run_flow(test_db, user_id)
    expected_empty: list[dict[str, Any]] = []
    assert llm_server.chat_requests == expected_empty, "the LLM was called"


@pytest.mark.parametrize("run_flow", _REJECTED_FLOWS, ids=_REJECTED_IDS)
@pytest.mark.asyncio
async def test_rejected_message_starts_no_llm_stream(
    test_db: Database,
    run_flow: Callable[[Database, int], Awaitable[FlowRun]],
) -> None:
    user_id = 712345635
    _session, llm_server = await run_flow(test_db, user_id)
    started = llm_server.stream_started.is_set()
    assert started is False, "the LLM stream started for a rejected message"


@pytest.mark.parametrize("run_flow", _REJECTED_FLOWS, ids=_REJECTED_IDS)
@pytest.mark.asyncio
async def test_rejected_message_stores_no_exchange(
    test_db: Database,
    run_flow: Callable[[Database, int], Awaitable[FlowRun]],
) -> None:
    user_id = 712345636
    await run_flow(test_db, user_id)
    expected_empty: list[tuple[str, Any]] = []
    history = await _history_pairs(test_db, user_id)
    assert history == expected_empty, "the rejected exchange was stored"


@pytest.mark.parametrize(
    "run_flow",
    [_run_llm_failure_flow, _run_document_failure_flow],
    ids=["llm-offline", "document-service-offline"],
)
@pytest.mark.asyncio
async def test_failed_message_edits_no_message(
    test_db: Database,
    run_flow: Callable[[Database, int], Awaitable[FlowRun]],
) -> None:
    user_id = 712345664
    session, _llm = await run_flow(test_db, user_id)
    expected_empty: list[EditMessageText] = []
    assert _requests_of(session, EditMessageText) == expected_empty, (
        "a message was edited"
    )


@pytest.mark.asyncio
async def test_blocked_user_causes_no_other_telegram_request(
    test_db: Database,
) -> None:
    user_id = 712345633
    session, _llm = await _run_blocked_flow(test_db, user_id)
    expected_count = 1
    assert len(session.requests) == expected_count, "the bot did more than deny"


@pytest.mark.asyncio
async def test_throttled_user_gets_answers_only_below_the_limit(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 712345683
    questions = [f"Question {index}" for index in range(1, 12)]
    session, _llm = await _run_throttled_flow(test_db, monkeypatch, user_id, questions)
    expected_count = 10
    assert len(_sent_messages(session)) == expected_count, "the throttle let too many"


@pytest.mark.asyncio
async def test_throttled_user_reaches_the_llm_only_below_the_limit(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 712345641
    questions = [f"Вопрос номер {index}" for index in range(1, 12)]
    _session, llm_server = await _run_throttled_flow(
        test_db, monkeypatch, user_id, questions
    )
    expected_count = 10
    assert len(llm_server.chat_requests) == expected_count, "the LLM got too many"


@pytest.mark.asyncio
async def test_throttled_user_still_starts_the_llm_stream(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 712345642
    questions = [f"Ask {index}" for index in range(1, 12)]
    _session, llm_server = await _run_throttled_flow(
        test_db, monkeypatch, user_id, questions
    )
    started = llm_server.stream_started.is_set()
    assert started is True, "no allowed question reached the LLM"


@pytest.mark.asyncio
async def test_throttled_user_stores_only_the_allowed_exchanges(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = 712345643
    allowed_questions = [f"Question {index}" for index in range(1, 11)]
    blocked_question = "Question 11"
    answer = "Hello, world!"
    await _run_throttled_flow(
        test_db, monkeypatch, user_id, [*allowed_questions, blocked_question]
    )
    expected = [
        entry
        for question in allowed_questions
        for entry in (("user", question), ("assistant", answer))
    ]
    history = await _history_pairs(test_db, user_id)
    assert history == expected, "the throttled question was stored"


@pytest.mark.asyncio
async def test_long_answer_is_split_into_multiple_telegram_messages(
    test_db: Database,
) -> None:
    user_id = 712345651
    response = " ".join(["long-answer"] * 1200)
    user_text = "Опиши всё подробно."
    session, _llm = await _run_text_flow(test_db, user_id, (response,), user_text)
    expected_count = 4
    assert len(_sent_messages(session)) == expected_count, "wrong number of parts"


@pytest.mark.asyncio
async def test_long_answer_sends_text_in_every_part(test_db: Database) -> None:
    user_id = 712345652
    response = " ".join(["very-long-part"] * 1000)
    user_text = "Дай развёрнутый ответ."
    session, _llm = await _run_text_flow(test_db, user_id, (response,), user_text)
    empty_parts = [request for request in _sent_messages(session) if not request.text]
    expected_empty: list[SendMessage] = []
    assert empty_parts == expected_empty, "a part of the long answer has no text"


@pytest.mark.asyncio
async def test_long_answer_parts_fit_into_telegram_messages(
    test_db: Database,
) -> None:
    user_id = 712345653
    response = " ".join(["oversized-answer"] * 900)
    user_text = "Не экономь слова."
    session, _llm = await _run_text_flow(test_db, user_id, (response,), user_text)
    oversized = [
        request.text
        for request in _sent_messages(session)
        if len(request.text) > MAX_MESSAGE_LENGTH
    ]
    expected_empty: list[str] = []
    assert oversized == expected_empty, "a part exceeds the Telegram message limit"


@pytest.mark.asyncio
async def test_long_answer_parts_join_into_the_answer(test_db: Database) -> None:
    user_id = 712345654
    response = " ".join(["long-answer"] * 1200)
    user_text = "Напиши очень длинный ответ."
    session, _llm = await _run_text_flow(test_db, user_id, (response,), user_text)
    delivered = " ".join(request.text for request in _sent_messages(session))
    assert delivered == response, "the parts do not add up to the answer"


@pytest.mark.asyncio
async def test_long_answer_is_stored_whole(test_db: Database) -> None:
    user_id = 712345655
    user_text = "Напиши очень длинный ответ."
    response = " ".join(["stored-answer"] * 1100)
    await _run_text_flow(test_db, user_id, (response,), user_text)
    expected = [("user", user_text), ("assistant", response)]
    history = await _history_pairs(test_db, user_id)
    assert history == expected, "the long answer was not stored whole"


@pytest.mark.parametrize(
    "run_flow",
    [
        partial(
            _run_text_flow,
            chunks=(" ".join(["long-answer"] * 1200),),
            user_text="Напиши очень длинный ответ.",
        ),
        partial(
            _run_history_limit_flow,
            previous_exchanges=[("Previous question 1", "Previous answer 1")],
            user_text="Use the recent talk.",
            response="Done.",
        ),
    ],
    ids=["long-answer", "history-limit"],
)
@pytest.mark.asyncio
async def test_long_or_limited_message_starts_the_llm_stream(
    test_db: Database,
    run_flow: Callable[[Database, int], Awaitable[FlowRun]],
) -> None:
    user_id = 712345684
    _session, llm_server = await run_flow(test_db, user_id)
    started = llm_server.stream_started.is_set()
    assert started is True, "the message did not reach the LLM"


@pytest.mark.asyncio
async def test_history_limit_sends_one_llm_request(test_db: Database) -> None:
    user_id = 712345688
    previous_exchanges = _previous_exchanges(2)
    _session, llm_server = await _run_history_limit_flow(
        test_db, user_id, previous_exchanges, "One request only.", "Single."
    )
    expected_count = 1
    assert len(llm_server.chat_requests) == expected_count, "not exactly one request"


@pytest.mark.asyncio
async def test_history_limit_sends_messages_as_a_list(test_db: Database) -> None:
    user_id = 712345689
    previous_exchanges = [("Earlier question", "Earlier answer")]
    _session, llm_server = await _run_history_limit_flow(
        test_db, user_id, previous_exchanges, "Check the payload.", "Listed."
    )
    request_messages = llm_server.chat_requests[0]["messages"]
    assert isinstance(request_messages, list), "the LLM messages are not a list"


@pytest.mark.parametrize(
    ("context_part", "expected_state"),
    [
        ("Previous question 1", "dropped"),
        ("Previous answer 1", "dropped"),
        ("Previous question 2", "dropped"),
        ("Previous answer 2", "dropped"),
        ("Previous question 3", "kept"),
        ("Previous answer 3", "kept"),
        ("Use only the recent conversation.", "kept"),
    ],
)
@pytest.mark.asyncio
async def test_history_limit_sends_only_the_latest_exchange_and_question(
    test_db: Database,
    context_part: str,
    expected_state: str,
) -> None:
    user_id = 712345690
    previous_exchanges = _previous_exchanges(3)
    user_text = "Use only the recent conversation."
    _session, llm_server = await _run_history_limit_flow(
        test_db, user_id, previous_exchanges, user_text, "History limit respected."
    )
    state = "kept" if context_part in _context_text(llm_server) else "dropped"
    assert state == expected_state, "the LLM context ignores the history limit"


@pytest.mark.asyncio
async def test_history_limit_sends_one_telegram_message(test_db: Database) -> None:
    user_id = 712345692
    previous_exchanges = [("Question before", "Answer before")]
    session, _llm = await _run_history_limit_flow(
        test_db, user_id, previous_exchanges, "Reply once.", "Once."
    )
    expected_count = 1
    assert len(_sent_messages(session)) == expected_count, "not exactly one reply"


@pytest.mark.asyncio
async def test_history_limit_delivers_the_complete_answer(test_db: Database) -> None:
    user_id = 712345693
    response = "History limit respected."
    previous_exchanges = [("First thing", "First reply"), ("Second thing", "Reply")]
    session, _llm = await _run_history_limit_flow(
        test_db, user_id, previous_exchanges, "Deliver it.", response
    )
    edited_texts = _edited_texts(session)
    delivered_text = (
        edited_texts[-1] if edited_texts else _sent_messages(session)[0].text
    )
    assert delivered_text == response, "the delivered answer is wrong"


@pytest.mark.asyncio
async def test_history_limit_preserves_the_whole_history(test_db: Database) -> None:
    user_id = 712345694
    previous_exchanges = _previous_exchanges(3)
    user_text = "Use only the recent conversation."
    response = "History limit respected."
    await _run_history_limit_flow(
        test_db, user_id, previous_exchanges, user_text, response
    )
    expected = [
        (role, content)
        for question, answer in (*previous_exchanges, (user_text, response))
        for role, content in (("user", question), ("assistant", answer))
    ]
    history = await _history_pairs(test_db, user_id)
    assert history == expected, "the limit removed stored history"
