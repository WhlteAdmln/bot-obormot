# Telegram LLM Bot

An asynchronous Telegram bot built with Python 3.11+ and aiogram 3. It provides private-chat access to a local language model through the OpenAI-compatible `llama-server` API, stores conversation history in SQLite, and can optionally process audio and documents through external services. Images, GIFs, animated stickers, and videos are handled locally.

For the module map and request flow, see [`docs/architecture.md`](docs/architecture.md). The Russian documentation is available in [`README.ru.md`](README.ru.md) and [`docs/architecture.ru.md`](docs/architecture.ru.md).

## Requirements

- Python 3.11 or newer.
- A Telegram bot token from [@BotFather](https://t.me/BotFather).
- A running `llama-server` exposing an OpenAI-compatible API.
- Optional Whisper and Document Engine services for audio transcription and document extraction.
- `ffmpeg` and `ffprobe` available on `PATH` for video and video-sticker processing.

## Installation

### Quick installation on Linux

The project provides an installer that downloads a published GitHub Release, checks the required system tools, creates a Python virtual environment, installs the locked dependencies, and prepares the configuration file. The default installation directory is `~/bot-obormot`.

Install the latest stable release:

```bash
curl -fsSL https://raw.githubusercontent.com/WhlteAdmln/bot-obormot/main/install.sh | sh -s -- --latest
```

Install the latest published GitHub prerelease (the newest release marked as a prerelease):

```bash
curl -fsSL https://raw.githubusercontent.com/WhlteAdmln/bot-obormot/main/install.sh | sh -s -- --nightly
```

Add `--systemd` to create a per-user systemd unit at `~/.config/systemd/user/bot-obormot.service`:

```bash
curl -fsSL https://raw.githubusercontent.com/WhlteAdmln/bot-obormot/main/install.sh | sh -s -- --latest --systemd
# or
curl -fsSL https://raw.githubusercontent.com/WhlteAdmln/bot-obormot/main/install.sh | sh -s -- --nightly --systemd
```

The installer must be run as a regular user, not as root. It uses `sudo` only when system packages need to be installed. It supports APT, DNF/YUM, Pacman, Zypper, and APK package managers. It checks for Python 3.11+, `pip`/`venv`, `unzip`, `curl`, build tools, CMake, and FFmpeg tools. On distributions whose repositories provide Python older than 3.11, install Python 3.11 or newer first. FFmpeg installation is best-effort; video processing will be unavailable if `ffmpeg`/`ffprobe` are missing.

The installer creates `~/bot-obormot`, renames `.env.example` to `.env`, sets restrictive permissions on `.env`, creates `.venv`, and installs packages from `requirements-lock.txt`. It does not overwrite an existing installation directory. Back up or move an existing directory before reinstalling.

After installation, edit the configuration and set at least `BOT_TOKEN` and `SUPERVISOR_ID`:

```bash
nano ~/bot-obormot/.env
```

When `--systemd` is used, the unit is created and systemd reloads its unit files, but the service is deliberately not enabled or started before `.env` is configured. After editing `.env`, run:

```bash
systemctl --user enable --now bot-obormot.service
systemctl --user status bot-obormot.service
journalctl --user -u bot-obormot.service -f
```

To start a user service at boot without an interactive login, an administrator may enable lingering for the account:

```bash
sudo loginctl enable-linger "$USER"
```

Optional installer environment variables:

- `BOT_INSTALL_DIR` — choose a different installation directory.
- `BOT_GITHUB_REPOSITORY` — override the default GitHub repository (`WhlteAdmln/bot-obormot`).
- `GITHUB_TOKEN` — provide a GitHub token if API rate limits or a private repository require authentication. Keep the token private and avoid placing it directly in shell history.

For a safer alternative to piping directly into a shell, download and inspect the installer first:

```bash
curl -fsSLo install.sh https://raw.githubusercontent.com/WhlteAdmln/bot-obormot/main/install.sh
less install.sh
sh install.sh --latest
```

### Manual installation

For a manual installation, run commands from the project root — the directory containing `requirements.txt`, `bot/`, and `prompts/`.

```bash
python3 -m venv .venv
source .venv/bin/activate
# Windows: .venv\\Scripts\\activate

python -m pip install -r requirements-lock.txt
cp .env.example .env
```

Edit `.env` and set at least:

- `BOT_TOKEN` — the token obtained from @BotFather;
- `SUPERVISOR_ID` — the numeric Telegram ID of the main administrator.

Replace the sample values in `.env.example`; they are placeholders, not working credentials. The application loads `.env` only from the project root (`PROJECT_ROOT/.env`), not from parent directories. The token format is checked before the Telegram Bot object is created.

Keep `.env`, API keys, the SQLite database, and user data private. Do not commit or publish them. On Linux/macOS, restrict an existing `.env` file with `chmod 600 .env`; startup applies `umask 0o077` for files and directories created by the process.

## Configuration

All settings are optional except `BOT_TOKEN` and `SUPERVISOR_ID`. Defaults below match `bot/config/settings.py` and `.env.example`.

| Variable | Default | Purpose |
|---|---:|---|
| `BOT_TOKEN` | — | Required Telegram bot token. Must match the expected numeric-ID/secret format. |
| `SUPERVISOR_ID` | — | Required positive numeric Telegram ID of the main administrator. |
| `ADMIN_IDS` | empty | Initial administrator IDs, comma-separated; imported into SQLite by the one-time migration. |
| `ALLOWED_USERS` | empty | Static allowlist, comma-separated. When empty, only the Supervisor and database administrators are admitted unless `ALLOW_ALL_USERS=true`. |
| `ALLOW_ALL_USERS` | `false` | Opens the bot to every non-blocked user when set to `true`. Keep `false` unless public access is intentional. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |
| `DATABASE_PATH` | `data/bot.db` | SQLite database path. The image directory is created beside the database as `images/`. |
| `LLM_BASE_URL` | `http://127.0.0.1:8080/v1` | Base URL of the OpenAI-compatible `llama-server` API. |
| `LLM_API_KEY` | `not-needed` | Optional Bearer token for `llama-server`; no authorization header is sent for an empty value or `not-needed`. |
| `LLM_MODEL` | `local-model` | Model name sent to the server. |
| `LLM_TEMPERATURE` | `0.7` | Generation temperature; must be non-negative. |
| `LLM_TOP_P` | `0.9` | Sampling parameter from 0 to 1. |
| `LLM_MAX_TOKENS` | `2048` | Maximum number of generated tokens. |
| `LLM_TIMEOUT` | `300` | LLM request timeout in seconds. |
| `LLM_MAX_CONCURRENT_GENERATIONS` | `1` | Maximum concurrent LLM generations. |
| `MAX_HISTORY_EXCHANGES` | `1000` | Maximum history limit administrators can assign. A normal user's default limit is 30 exchanges. |
| `MAX_STORED_EXCHANGES` | `2000` | Maximum number of full user/assistant exchanges retained per user (up to 4,000 message rows). Older rows and their managed images are pruned after a successful response. |
| `STREAM_UPDATE_INTERVAL` | `1.0` in `.env.example` | Kept and validated as a configuration value for compatibility. The active Telegram streaming interval is currently fixed at 0.8 seconds in `bot/services/chat/streaming/settings.py`. |
| `WHISPER_API_URL` | empty | Optional Whisper endpoint. Audio processing is unavailable when unset. |
| `WHISPER_API_KEY` | empty | Optional Bearer token sent to Whisper. |
| `WHISPER_TIMEOUT` | `180` | Whisper request timeout in seconds. |
| `DOCUMENT_API_URL` | empty | Optional Document Engine endpoint. Document processing is unavailable when unset. |
| `DOCUMENT_API_KEY` | empty | Optional Bearer token sent to Document Engine. |
| `DOCUMENT_TIMEOUT` | `300` | Document Engine request timeout in seconds. |

Some important limits are code constants rather than environment settings:

- `DEFAULT_HISTORY_EXCHANGES = 30` — normal user's default history limit.
- `MAX_CONTEXT_EXCHANGES = 100` — hard cap on the number of exchanges loaded for one LLM request, regardless of the user's larger saved history limit.
- `MAX_INPUT_TEXT_LENGTH = 12,288` characters — final input text validation limit.
- Incoming Telegram media: 20 MiB maximum per file and at most 3 simultaneous downloads.

`MAX_HISTORY_EXCHANGES`, `MAX_CONTEXT_EXCHANGES`, and `MAX_STORED_EXCHANGES` serve different purposes: user-configurable history limit, per-request context cap, and long-term storage cap, respectively.

## Run

```bash
python -m bot.main
```

The startup sequence is: set the restrictive process umask, configure logging and secret filtering, configure Pillow limits, validate/log the access mode, validate the Telegram token, connect SQLite and apply schema migrations, start the LLM client, start periodic image cleanup, and begin Telegram polling. Shutdown cancels background cleanup and closes the LLM client, database connection, and Telegram session.

The bot is designed for private chats. Messages from groups/supergroups/channels and events without a known sender are not passed to chat handlers; history and personal prompts are user-scoped rather than chat-scoped.

## Check `llama-server`

```bash
curl http://127.0.0.1:8080/v1/models
```

Change `LLM_BASE_URL` if the server uses another address or port. If authentication is enabled on `llama-server`, set the same secret in `LLM_API_KEY`. Prefer binding the LLM server to localhost or a trusted private interface; do not expose it directly to the public internet.

## Telegram commands

### Available to users

| Command | Purpose |
|---|---|
| `/start` | Show help and set the user's command menu. |
| `/history` | Show the current personal history limit. |
| `/history_limit N` | Set the caller's history limit. Non-admin users are limited to the standard maximum; administrators can use `MAX_HISTORY_EXCHANGES`. |
| `/history_clear` | Delete conversation history and its managed images. |
| `/forget_me` | Delete conversation history, managed images, personal system prompt, and personal history-limit setting. This does not revoke access or change administrator/block lists. |
| `/prompt` | Show the effective system prompt. |
| `/prompt_set` | Start setting a personal system prompt. |
| `/prompt_reset` | Remove the personal prompt and return to the default prompt. |
| `/cancel` | Cancel prompt entry while the relevant FSM state is active. |

### Available to administrators and the Supervisor

| Command | Purpose |
|---|---|
| `/health` | Check Telegram API, SQLite, and LLM availability. |
| `/history_limit USER_ID N` | Set another user's history limit. |
| `/ban USER_ID` | Block a non-admin user immediately; a blocked user cannot use the bot. |
| `/unban USER_ID` | Remove a user's block. |

### Supervisor only

| Command | Purpose |
|---|---|
| `/admin` | Show the administration panel. |
| `/admins` | List database administrators. |
| `/admin_add USER_ID` | Add a database administrator. |
| `/admin_remove USER_ID` | Remove a database administrator. |

Administrators cannot ban the Supervisor or another database administrator. Remove an administrator with `/admin_remove` before banning that user. The Supervisor cannot be banned. Administrator management, bans/unbans, changes to another user's history limit, and denied calls to administrative handlers are written as `AUDIT` log records.

## Tests

Install the pinned runtime dependencies and development tools:

```bash
python -m pip install -r requirements-dev.txt
```

Run the regular test suite:

```bash
python -m pytest -q
```

Tests marked `integration` that require a running `llama-server` are run separately:

```bash
python -m pytest -m integration -q
```

The default `pytest.ini` configuration excludes integration tests, so the normal suite does not require an external LLM service.

## Project structure

```text
bot/
├── app/             # startup, lifecycle, routing, logging, background jobs
├── config/          # .env loading, settings, paths, default system prompt
├── errors/          # application exception types
├── fsm/             # aiogram FSM states and keys
├── handlers/        # start, admin, history, prompt, chat, fallback handlers
├── middlewares/     # throttling, access checks, temporary-message cleanup
├── services/
│   ├── access/      # role and access decisions
│   ├── audio/       # Whisper client and audio input preparation
│   ├── chat/        # aggregation, input preparation, pipeline, streaming, errors
│   ├── database/    # SQLite facade, repositories, use cases, image storage
│   ├── documents/   # Document Engine client and response validation
│   ├── llm/         # llama-server client, context fitting, tokenization, streaming
│   ├── media/       # image/GIF/TGS/video inspection and processing
│   └── telegram/    # Telegram downloads and chat actions
└── utils/           # audit logging, secret filtering, safe log text

docs/                # architecture documentation
prompts/             # default system prompt
tests/               # unit and integration tests
```

See [`docs/architecture.md`](docs/architecture.md) for request flow, storage boundaries, concurrency limits, and security controls.

## Security baseline

The application includes the following hardening measures:

- **Access control:** closed by default; private chats only; no-sender events are dropped; persistent SQLite blocks are checked for non-Supervisor users; denied notices are rate-limited. `ALLOW_ALL_USERS=true` is an explicit opt-in.
- **Abuse and resource limits:** 10 incoming events per user per 10 seconds, at most 3 queued/active chat requests per user, 20 MiB file downloads, at most 3 concurrent downloads, and bounded image/animation work.
- **Untrusted media:** content is sniffed from file bytes; Pillow decompression limits, GIF/TGS/video dimension and frame limits, `ffmpeg`/`ffprobe` timeouts, local-file-only protocol access, and bounded subprocess resources are applied.
- **External HTTP services:** Whisper and Document Engine responses are streamed with a 2 MiB success-body limit and a 2 KiB error-body read limit. Optional Bearer keys are supported. Use HTTPS when those services are remote.
- **LLM input:** known template/control-token strings are neutralized in non-system messages; document text, transcriptions, and captions are explicitly described as data in the default system prompt. This is defense in depth, not a guarantee against every prompt-injection technique.
- **Secrets and logs:** Telegram/API secrets are redacted by a logging filter; audio transcription text is not logged; user-controlled filenames/MIME metadata and service error details are sanitized before logging; admin operations use `AUDIT` records.
- **Local data:** startup uses `umask 0o077` on Unix-like systems; `.env` is loaded only from the project root; the Telegram token format is validated; image deletion is restricted to managed UUID-named files inside the configured image directory.
- **Retention:** no more than `MAX_STORED_EXCHANGES` full exchanges are retained per user; managed images linked to old messages are pruned. A daily job removes image media older than 30 days and orphaned managed files older than a 24-hour grace period.

For production, install exact versions from `requirements-lock.txt`. `requirements.txt` defines supported version ranges for flexible installs. At least monthly, check the lock file for known advisories:

```bash
python -m pip install pip-audit
pip-audit -r requirements-lock.txt
```

Review each finding, update affected dependencies deliberately, and run the full test suite before deployment. `pip-audit` reports known advisories; it does not prove that the application or its dependencies are vulnerability-free.

For existing deployments, `umask` does not change permissions on files already present. On Linux/macOS, review and restrict existing data and secrets, for example:

```bash
chmod -R go-rwx data
chmod 600 .env
```

Never publish `.env`, Telegram tokens, API keys, user databases, or application logs containing operational data. `SUPERVISOR_ID` must identify a trusted account with full administrative control.
