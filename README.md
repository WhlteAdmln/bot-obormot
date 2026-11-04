# Telegram LLM Bot

An asynchronous Telegram bot built with Python 3.11+ and aiogram. It stores history in SQLite, interacts with a local LLM via the OpenAI‑compatible `llama-server` API, and, when additional services are configured, processes audio, documents, images, and animations.

## Requirements

- Python 3.11 or newer.
- Telegram bot token from [@BotFather](https://t.me/BotFather).
- Available `llama-server` with an OpenAI-compatible API.
- Additional Whisper and Document Engine services are needed only for the corresponding functions.

## Installation

Commands are executed from the `telegram_bot` directory — the one where `requirements.txt`, `bot/`, and `prompts/` are located.

```bash
python3 -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate

python -m pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and be sure to fill in:

- `BOT_TOKEN` — the token obtained from @BotFather;
- `SUPERVISOR_ID` — your numeric Telegram ID.

The remaining parameters can be left with the values from the example and changed as needed. The `.env.example` file contains all supported environment settings and secure template values. The `.env` file itself contains local secrets and should not be shared with other users or included in published archives.

You can find out your numeric Telegram ID using a special Telegram bot, for example @userinfobot. Before running the script, replace the string `REPLACE_WITH_NUMERIC_TELEGRAM_ID` with a number.

## Configuration

| Variable | Required | Default value / purpose |
|---|---:|---|
| `BOT_TOKEN` | Yes | Telegram bot token. |
| `SUPERVISOR_ID` | Yes | Positive numeric Telegram ID of the main administrator. |
| `ADMIN_IDS` | No | Additional administrators separated by commas; on the first run, they are used by the existing SQLite migration. |
| `ALLOWED_USERS` | No | Allowed users separated by commas. An empty value grants access to everyone; administrators have access regardless of the list. |
| `LOG_LEVEL` | No | `INFO`; allowed levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `DATABASE_PATH` | No | `data/bot.db`; path to SQLite. The directory for the file is created by the application. |
| `LLM_BASE_URL` | No | `http://127.0.0.1:8080/v1`; base URL for the OpenAI‑compatible API. |
| `LLM_API_KEY` | No | `not-needed`; value for the authorization header if the server requires it. |
| `LLM_MODEL` | No | `local-model`; the model name passed to the server. |
| `LLM_TEMPERATURE` | No | `0.7`; generation temperature, not less than zero. |
| `LLM_TOP_P` | No | `0.9`; a value from 0 to 1. |
| `LLM_MAX_TOKENS` | No | `2048`; maximum number of generated tokens. |
| `LLM_TIMEOUT` | No | `300`; LLM request timeout in seconds. |
| `LLM_MAX_CONCURRENT_GENERATIONS` | No | `1`; maximum number of simultaneous generations. |
| `MAX_HISTORY_EXCHANGES` | No | `1000`; upper limit of the user history limit. The standard limit of the app is 30 full exchanges. |
| `WHISPER_API_URL` | No | Empty; URL of the Whisper API. If the value is empty, audio processing is not available. |
| `WHISPER_TIMEOUT` | No | `180`; Whisper timeout in seconds. |
| `DOCUMENT_API_URL` | No | Empty; URL Document Engine. If the value is empty, document processing is not available. |
| `DOCUMENT_TIMEOUT` | No | `300`; Document Engine timeout in seconds. |

Additional: the limit on the extracted user text is set in the code and currently stands at 12,288 characters. The `STREAM_UPDATE_INTERVAL` parameter is still present in the configuration object for compatibility, but the actual streaming response update interval is now set in the streaming module and equals 0.8 seconds; the environment variable does not affect it.

## Launch

From the project root:

```bash
python -m bot.main
```

The order of application startup is: connecting to SQLite, launching the LLM client, launching background image cleaning, then Telegram polling. Upon completion, the application stops the background task and closes the LLM, SQLite, and Telegram session.

## Checking `llama-server`

```bash
curl http://127.0.0.1:8080/v1/models
```

If the server uses a different address or port, change `LLM_BASE_URL` in `.env`. If the server requires a specific model name, specify it in `LLM_MODEL`.

## Bot commands

- `/start` — help and available commands.
- `/history` — current history limit.
- `/history_limit` — change the history limit.
- `/history_clear` — clear the conversation history.
- `/prompt` — show the system prompt.
- `/prompt_set` — start setting the system prompt.
- `/prompt_reset` — reset the user system prompt.
- `/cancel` — cancel entering the prompt in the corresponding FSM state.
- `/health` — status of external components (administrative command).
- `/admin`, `/admins`, `/admin_add`, `/admin_remove` — manage administrators.

## Tests

Install development dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

The standard set of tests:

```bash
python -m pytest -q
```

Integration tests that require a running `llama-server` are run separately:

```bash
python -m pytest -m integration -q
```

By default, `pytest.ini` excludes tests with the `integration` marker, so a regular run does not depend on the availability of an external LLM.

## Project Structure

A detailed map of the modules and their responsibilities is located in [`docs/architecture.md`](docs/architecture.md).

The system prompt is loaded when importing the configuration from `prompts/systemPrompt.md`; the file must be present. The history and related image files are stored locally next to the SQLite database. Background cleanup runs once a day; the current parameters are 30 days for storing links to old images and a 24‑hour protection period for orphaned files.

## Security

- Do not publish `.env`, Telegram tokens, API keys, and custom SQLite databases.
- Do not share secrets in issues, logs, or source code archives.
- Do not expose the `llama-server` port to the internet without separate authentication and network protection.
- `SUPERVISOR_ID` must point to a trusted account: it gains full administrative control over the bot.
