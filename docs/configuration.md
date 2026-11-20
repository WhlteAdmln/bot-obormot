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
| `LLM_MAX_TOKENS` | `2048` | Maximum number of generated tokens. Reasoning models spend part of this limit on thinking, so raise it (for example to `8192`) if answers come back empty or cut off. |
| `LLM_TIMEOUT` | `300` | Request timeout in seconds. |
| `LLM_CONTEXT_SIZE` | empty | Context size in tokens. Set it when the server does not report it. |
| `LLM_TOKEN_COUNTING` | `auto` | `auto`, `llamacpp` or `estimate`. |
| `LLM_MAX_CONCURRENT_GENERATIONS` | `1` | Number of generations that run at the same time. |
| `MAX_HISTORY_EXCHANGES` | `1000` | Upper bound of the per-user history limit. |
| `MAX_STORED_EXCHANGES` | `2000` | Number of exchanges kept per user in SQLite. |

### System prompt

The default system prompt is built into the package. To replace it without
changing the installation, point `SYSTEM_PROMPT_PATH` to your own file.

| Setting | Default | Description |
|---------|---------|-------------|
| `SYSTEM_PROMPT_PATH` | empty | UTF-8 text or Markdown file that replaces the built-in default system prompt. A relative path resolves against the home directory. Empty keeps the built-in prompt. |

To start from the built-in prompt, copy it into the home directory, set
`SYSTEM_PROMPT_PATH=systemPrompt.md` in `.env`, edit the file and restart the
service:

```sh
cd ~/bot-obormot
.venv/bin/python -c "from importlib.resources import files; print(files('bot_obormot').joinpath('prompts', 'systemPrompt.md').read_text(encoding='utf-8'))" > systemPrompt.md
```

- The file is read at startup. A missing, unreadable or empty file stops the
  bot with a configuration error, and `bot-obormot doctor` reports it.
- The file has no length limit. The 4000-character limit applies only to
  personal prompts that users set with `/prompt_set`.
- Personal prompts still override the default, and `/prompt_reset` returns a
  user to the prompt from this file.
- Keep the file outside the virtual environment, so reinstalling the package
  does not touch it.

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
