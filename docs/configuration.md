# Configuration

The bot reads its settings from environment variables. `bot-obormot init` creates
a protected `.env` file in the application home directory from the packaged
template. Run `bot-obormot config check` to validate the settings and
`bot-obormot doctor` to check the whole installation.

## Where files live

The application home directory is `BOT_OBORMOT_HOME` and defaults to
`~/bot-obormot` (`/data` in the Docker image). Relative paths in the settings
are resolved against it. The `.env` file is read from the home directory first,
then from the current working directory. Variables that are already set in the
process environment always win over `.env` values.

## Settings

Required settings are `BOT_TOKEN` and `SUPERVISOR_ID`. Every other setting has a
default.

### Telegram and access

| Setting | Default | Description |
|---------|---------|-------------|
| `BOT_TOKEN` | none | Telegram bot token from @BotFather. Required. |
| `SUPERVISOR_ID` | none | Numeric Telegram ID of the owner. Required. The supervisor is always allowed and manages the administrators. |
| `ADMIN_IDS` | empty | Comma-separated positive IDs of initial administrators. Administrators are stored in SQLite afterwards. |
| `ALLOWED_USERS` | empty | Comma-separated positive IDs of a static allowlist. An empty value does not make the bot public. |
| `ALLOW_ALL_USERS` | `false` | Set to `true` only to allow every user who is not blocked. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. |
| `DATABASE_PATH` | `data/bot.db` | SQLite database path, relative to the home directory. |

### LLM server

See [LLM servers](llm-servers.md) for server compatibility.

| Setting | Default | Description |
|---------|---------|-------------|
| `LLM_BASE_URL` | `http://127.0.0.1:8080/v1` | Base URL of the OpenAI-compatible server. |
| `LLM_API_KEY` | `not-needed` | API key sent as a bearer token. |
| `LLM_MODEL` | `local-model` | Model name sent in each request. |
| `LLM_TEMPERATURE` | `0.7` | Sampling temperature, 0 or higher. |
| `LLM_TOP_P` | `0.9` | Nucleus sampling, from 0 to 1. |
| `LLM_MAX_TOKENS` | `2048` | Maximum number of generated tokens. |
| `LLM_TIMEOUT` | `300` | Request timeout in seconds. |
| `LLM_CONTEXT_SIZE` | empty | Context size in tokens. Set it when the server does not report it. |
| `LLM_TOKEN_COUNTING` | `auto` | `auto`, `llamacpp` or `estimate`. |
| `LLM_MAX_CONCURRENT_GENERATIONS` | `1` | Number of generations that run at the same time. |
| `MAX_HISTORY_EXCHANGES` | `1000` | Upper bound of the per-user history limit. |
| `MAX_STORED_EXCHANGES` | `2000` | Number of exchanges kept per user in SQLite. |

### audiodoc (optional)

Audio transcription and document text extraction are provided by
[audiodoc](https://github.com/WhlteAdmln/audiodoc). Leave `AUDIODOC_URL` empty to
disable both features.

| Setting | Default | Description |
|---------|---------|-------------|
| `AUDIODOC_URL` | empty | Base URL of audiodoc, for example `http://127.0.0.1:8000`. |
| `AUDIODOC_AUDIO_KEY` | empty | API key for audio requests, if audiodoc requires one. |
| `AUDIODOC_DOCUMENT_KEY` | empty | API key for document requests, if audiodoc requires one. |
| `AUDIODOC_AUDIO_TIMEOUT` | `180` | Audio request timeout in seconds. |
| `AUDIODOC_DOCUMENT_TIMEOUT` | `300` | Document request timeout in seconds. |

## Deprecated names

These names are read only when the matching new setting is empty. Each use
logs a deprecation line. They will be removed in 0.3.0.

| Old name | Use instead |
|----------|-------------|
| `WHISPER_API_URL` | `AUDIODOC_URL` |
| `WHISPER_API_KEY` | `AUDIODOC_AUDIO_KEY` |
| `WHISPER_TIMEOUT` | `AUDIODOC_AUDIO_TIMEOUT` |
| `DOCUMENT_API_URL` | `AUDIODOC_URL` |
| `DOCUMENT_API_KEY` | `AUDIODOC_DOCUMENT_KEY` |
| `DOCUMENT_TIMEOUT` | `AUDIODOC_DOCUMENT_TIMEOUT` |

## Home directory

| Setting | Default | Description |
|---------|---------|-------------|
| `BOT_OBORMOT_HOME` | `~/bot-obormot` | Application home directory. It holds `.env`, `data/` and the virtual environment. |
