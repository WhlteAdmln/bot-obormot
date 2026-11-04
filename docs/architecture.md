# Project Architecture

This document describes the current implementation after the security-hardening work and the removal of obsolete compatibility shims. It is intended to be used together with [`../README.md`](../README.md), which covers installation, environment variables, and operator commands.

## 1. Runtime overview

The bot is an asynchronous Python 3.11+ application built on aiogram 3. Telegram updates are handled in private chats. Conversation state is keyed by Telegram `user_id`, not by chat, so group messages are intentionally ignored.

```text
Telegram private message
  │
  ▼
ThrottleMiddleware (10 events / 10 seconds / user)
  │
  ▼
AccessMiddleware (private chat, sender, block list, role/allowlist)
  │
  ▼
TemporaryMessagesCleanupMiddleware
  │
  ▼
Root routers: start → admin → commands → chat
  │
  └─ chat handler
       ├─ inspect_message
       ├─ aggregate long plain-text parts (3-second continuation window)
       ├─ enforce per-user pending-request limit and lock
       ├─ prepare text/audio/media/document input
       ├─ process_chat: history → context fitting → LLM stream → DB save/prune
       └─ deliver the final Telegram response
```

`bot/app/routers.py` is the single registration point. Middleware order is significant: throttling runs before access checks; temporary-message cleanup runs after access. Root router order is `start`, `admin`, `commands`, then `chat`, with the general chat handler last so command handlers get the first opportunity to match.

## 2. Startup and shutdown

- `bot/main.py` is the executable entry point.
- `bot/app/bootstrap.py` applies `umask(0o077)`, configures logging and secret filtering, enables Pillow limits, logs the access mode, validates `BOT_TOKEN`, creates the Bot/Dispatcher, and configures routers.
- `bot/app/lifecycle.py` connects SQLite, starts the LLM client, starts the named periodic image-cleanup task, and starts Telegram polling. On shutdown it cancels and awaits cleanup, then closes the LLM client, database connection, and Telegram session.
- `bot/app/background/image_cleanup.py` invokes image cleanup once per day with a 30-day media-retention period and a 24-hour grace period for orphaned images.
- `bot/config/__init__.py` loads only `PROJECT_ROOT/.env` before importing the settings object. It does not search parent directories.

## 3. Telegram layer, access, and administration

### Middleware and access rules

- `bot/middlewares/throttle.py` permits up to 10 message events per user in a rolling 10-second window. It keeps a bounded LRU-like record for at most 5,000 users and silently drops excess events.
- `bot/middlewares/access.py` rejects events without a sender and ignores non-private chats. Denial notifications are sent at most once per user per 60 seconds; the tracking dictionary is bounded.
- `bot/services/access/roles.py` contains pure Supervisor/admin/allowlist membership helpers.
- `bot/services/access/service.py` applies access policy. The Supervisor is always admitted. For other users, persistent SQLite blocks are checked before database-admin, `ALLOW_ALL_USERS`, and `ALLOWED_USERS` admission.
- `bot/services/chat/locks.py` serializes work per user and counts active/waiting requests. `bot/handlers/chat/handler.py` allows at most 3 pending/active requests for one user.

The default access mode is closed: with an empty `ALLOWED_USERS` and `ALLOW_ALL_USERS=false`, only the Supervisor and database administrators can use the bot. `ALLOW_ALL_USERS=true` is an explicit opt-in. `/ban` cannot target the Supervisor or a database administrator; administrators must first be removed with `/admin_remove`. The Supervisor bypasses normal block checks and cannot be blocked through the command or database facade.

### Handler packages

- `bot/handlers/start/` — `/start`, per-chat command menu, and help text.
- `bot/handlers/admin/` — `/health`, `/admin`, `/admins`, `/admin_add`, `/admin_remove`, `/ban`, `/unban`.
- `bot/handlers/history/` — `/history`, `/history_limit`, `/history_clear`, `/forget_me`.
- `bot/handlers/prompt/` — `/prompt`, `/prompt_set`, `/prompt_reset`, `/cancel`, and prompt FSM handling.
- `bot/handlers/chat/` — incoming-message coordination and Telegram response delivery.
- `bot/handlers/fallback/` — fallback handling for unsupported input/states.
- `bot/handlers/commands/__init__.py` is only a router aggregator. It exports `router`; it is not a compatibility-shim collection.

Administrative actions use `bot/utils/audit.py` and emit `AUDIT action=... actor=... target=... result=...` records. Admin add/remove, ban/unban, history-limit changes for another user, and denied calls to administrative handlers are logged.

## 4. Chat and LLM request pipeline

### Input preparation

`bot/services/chat/input/` separates inspection, preparation, content construction, saved-history text, and media/audio/document parts. `prepare_message()` orchestrates audio, media, and document handling. User content and saved text are separate values: multimodal payloads can be sent to the model while the database stores a textual representation plus media references.

Long plain-text messages are combined by `bot/services/chat/aggregation/aggregator.py`. Only ordinary text messages are aggregated; audio, media, and documents are not. The continuation window is 3 seconds. The aggregator retains strong references to its background tasks and uses `MAX_INPUT_TEXT_LENGTH` as the threshold for refusing further continuation; the final combined text is validated against 12,288 characters.

`bot/services/chat/locks.py` serializes each user's chat processing. The chat handler caps active plus waiting requests at 3 per user. `ThrottleMiddleware` independently caps incoming message-event frequency.

### LLM processing

`bot/services/chat/pipeline.py`:

1. Loads the user's effective system prompt.
2. Loads the user's history limit and caps it at `MAX_CONTEXT_EXCHANGES = 100`.
3. Retrieves recent full exchanges from SQLite.
4. Calls `llm_client.fit_messages_to_context()` to fit the request to the model's context window.
5. Streams the model response and sends partial updates through the callback.
6. Saves the exchange to SQLite and invokes history pruning. A pruning error is logged but does not discard an otherwise successful response.

`bot/services/llm/` contains the OpenAI-compatible client, HTTP session/auth headers, endpoints, message normalization, context fitting, tokenization, context-size queries, and streaming. `normalize_messages()` neutralizes known template/control-token strings in every non-system message, including text parts of multimodal messages. System prompts are left unchanged. This is a defense-in-depth measure; it is not a complete prompt-injection solution.

The default system prompt is stored in `prompts/systemPrompt.md`; users may have a personal system prompt. The default prompt explicitly frames document text, speech transcriptions, and captions as data to analyze rather than instructions. Model output is formatted/escaped before being sent to Telegram.

## 5. Media and external services

### Telegram downloads and local media processing

`bot/services/telegram/downloader.py` requires a known positive Telegram file size, limits each file to 20 MiB, writes through a size-limited buffer, and allows at most 3 simultaneous downloads.

`bot/services/media/` detects actual media type from file bytes instead of trusting only a filename or MIME declaration. It prepares images and dispatches animations to `bot/services/media/animation/`:

- Pillow image processing uses a 40-million-pixel safety limit; GIF logical canvases are limited to 16 million pixels and GIFs to 2,000 frames.
- At most 3 image jobs run concurrently.
- TGS files are limited to 256 KiB compressed, 4 MiB decompressed JSON, and a 1,024-pixel canvas side before data is passed to `rlottie`.
- Video containers are checked as WEBM/MP4. `ffprobe` and `ffmpeg` are limited by a 30-second process timeout; protocol access is restricted to local files; decoding is limited to one thread; source video frames are capped at a 3,840 × 2,160 pixel-count budget, duration at 30 seconds, extraction at 6 frames, and one allocation is capped at 1 GiB.
- At most 2 animation jobs run concurrently.

The video path requires `ffmpeg` and `ffprobe` on `PATH`.

### Whisper and Document Engine

- `bot/services/audio/client.py` sends audio to Whisper; `bot/services/documents/client.py` sends documents to Document Engine and validates the returned structure.
- Both services are optional and disabled when their URL is empty.
- `WHISPER_API_KEY` and `DOCUMENT_API_KEY` add optional Bearer authorization headers. Use HTTPS when either service is remote; API keys do not encrypt HTTP traffic.
- `bot/services/http_limits.py` reads response bodies incrementally in 64 KiB chunks, with a 2 MiB limit for successful service responses and a 2 KiB limit for HTTP error-body reads.

## 6. SQLite and local files

`bot/services/database/` is organized around a `Database` facade, repositories, use cases, SQL queries, and file storage.

- `facade.py` exposes the application-level database API and serializes operations with a shared `asyncio.Lock`.
- `connection.py` opens SQLite with foreign keys enabled, WAL journal mode, a 5-second connection timeout, and a 5-second busy timeout.
- `schema.py` creates tables for messages, message media, user prompts/settings, personal history limits, administrators, blocked users, and migration tracking. `repositories/blocked_users.py` provides persistent block-list operations.
- `repositories/` contains parameterized SQL operations; `usecases/` coordinates multi-step history, exchange, and cleanup behavior.
- `decorators.py` translates SQLite errors to application database errors and attempts a rollback after failed operations so the connection can accept subsequent writes.
- `files/image_storage.py` reads/writes/deletes local image files. Managed image names are UUID hex strings with a `.jpg` suffix and must be direct children of the configured `images/` directory before cleanup/reset/pruning is allowed to delete them.

The image directory is `Path(DATABASE_PATH).resolve().parent / "images"`. `MAX_STORED_EXCHANGES` limits retention to 2,000 exchanges per user by default (up to 4,000 individual messages). Pruning runs after a successful exchange and removes older messages plus their managed images. `/history_clear` removes conversation history; `/forget_me` additionally removes the personal system prompt and personal history limit. Neither command revokes allowlist/admin/block status.

The daily image cleanup removes media references/images older than 30 days and unreferenced managed images only after a 24-hour orphan grace period. Old text messages are not removed by the 30-day media cleanup; long-term text retention is governed by `MAX_STORED_EXCHANGES` and user deletion commands.

## 7. Logging and security controls

- `bot/app/logging_setup.py` configures root logging and attaches `SecretsFilter` to root handlers. Telegram token patterns and configured LLM/Whisper/Document Engine secrets are redacted from log messages and exception text.
- `bot/utils/text.py::log_safe()` escapes CR/LF, replaces non-printable characters, and truncates user-controlled log fields. Audio transcription content is not logged; only the character count is recorded. Service error details are sanitized before logging.
- `bot/utils/audit.py` writes administrator audit records under the `bot.audit` logger.
- `bot/config/settings.py` reads environment configuration; `bot/app/bootstrap.py` validates the Telegram token format before creating the Bot.
- Startup `umask(0o077)` protects newly created files/directories on Unix-like systems. It does not retroactively change permissions of existing database, image, or `.env` files.

The application still depends on host-level protection, correct `.env` permissions, network isolation for local services, and periodic dependency review with `pip-audit`. Automated tests and log filtering do not replace deployment review or manual Telegram checks.

## 8. Dependency and compatibility policy

- `requirements.txt` defines supported version ranges.
- `requirements-lock.txt` pins the runtime dependency set for reproducible production installs.
- `requirements-dev.txt` includes the locked runtime set plus pytest tooling.
- The obsolete `bot.services.*` compatibility shims were removed in the structural cleanup. No legacy service shims are part of the current source tree. Import code from its actual package (`bot.services.chat.input`, `bot.services.media`, `bot.services.chat.aggregation`, etc.).
- `bot/handlers/commands/__init__.py` remains solely as a root-router aggregator; old helper/FSM re-exports were removed.

Run the standard tests with `python -m pytest -q`. Run tests marked `integration` separately with `python -m pytest -m integration -q` when a compatible `llama-server` is available.
