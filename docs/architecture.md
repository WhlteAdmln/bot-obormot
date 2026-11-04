# Project Architecture

The document describes the module boundaries after structural refactoring. Public facades and compatible imports have been preserved for existing code and tests.

## Top Level

```text
bot/
├── app/                 # application build, startup and shutdown order
├── config/              # reading environment variables, paths, and system prompt
├── errors/              # types of application exceptions
├── fsm/                 # aiogram FSM keys and states
├── handlers/             # Telegram handlers grouped by purpose
├── middlewares/          # access middleware and temporary message cleaning
├── services/             # application services and integrations
└── utils/                # small common utilities
```

## Application and Telegram layer

- `bot/main.py` — a thin entry point; the application launch is assembled in `bot/app/bootstrap.py`.
- `bot/app/routers.py` — the only place where middleware and root routers are registered. The registration order is part of the behavior: `AccessMiddleware`, then `TemporaryMessagesCleanupMiddleware`; next are the routers `start`, `admin`, `commands`, `chat`.
- `bot/app/lifecycle.py` — setting up and shutting down SQLite, LLM, background cleanup, and Telegram session.
- `bot/handlers/` — commands, history, system prompt, administration, and chat processing.
- `bot/fsm/` — common states and FSM keys; `bot/middlewares/` — middleware.

## Services

### Database

`bot/services/database/` contains the `Database` facade, connection, schema and migrations, SQL repositories, queries, file storage and use cases.

- `facade.py` — public API and coordination of operations.
- `connection.py`, `schema.py`, `migrations/` — connection, SQLite structure and existing migrations.
- `repositories/`, `queries/` — SQL operations.
- `usecases/` — scenarios for recording exchanges, history, and image cleanup.
- `files/image_storage.py` — operations with local image files.

**Locking rule:** the shared `asyncio.Lock` belongs to the external facade/transactional layer. Repositories do not acquire this lock on their own. You cannot call another facade method from one locked facade method that re‑acquires the same non‑reentrant lock.

### LLM

`bot/services/llm/` contains the client, HTTP session, endpoints, message formatting, tokenization, context size determination, history fitting, and streaming generation.

`LLMClient` and `llm_client` remain the public access point; implementation details are distributed among the package modules.

### Chat

`bot/services/chat/` contains the pipeline, custom blocks, logging of incoming messages, aggregation, formatting, preparation of user input, error handling, and streaming responder.

`bot/handlers/chat/` is responsible for linking the Telegram event with the service pipeline and sending the result.

### Media, Audio, and Documents

- `bot/services/media/` — definition and preparation of multimodal content.
- `bot/services/media/animation/` — extracting GIF, TGS, and video frames, sampling, JPEG, and concurrency limits.
- `bot/services/audio/` — preparing audio messages and making a request to Whisper.
- `bot/services/documents/` — making a request to Document Engine and verifying its response.
- `bot/services/telegram/` — downloading Telegram files and handling chat actions.
- `bot/services/access/` — verifying roles and access rights.

## Compatibility

Some of the old modules `bot.services.*` and package facades have been left as re‑export points. This is intentional so that old imports and third‑party consumers of the project do not break when the code is reorganized internally. Such facades should be removed only as a separate change, with a check of all usage locations.

## Refactoring boundaries

This stage changed the structure and documentation, not the bot’s functional rules. Corrections for known behavioral inconsistencies (for example, the unused `STREAM_UPDATE_INTERVAL` setting, new HTTP sessions for Audio/Documents, or limit rules) should be planned separately and covered by independent tests.
