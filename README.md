# Telegram LLM Bot

An asynchronous Telegram bot built with Python 3.11+ and aiogram 3. It provides private-chat access to a language model through an OpenAI-compatible API, stores conversation history in SQLite, and can optionally process audio and documents through [audiodoc](https://github.com/WhlteAdmln/audiodoc). Images, GIFs, animated stickers, and videos are handled locally.

For the module map and request flow, see [`docs/architecture.md`](docs/architecture.md). The Russian documentation is available in [`README.ru.md`](README.ru.md) and [`docs/architecture.ru.md`](docs/architecture.ru.md).

## Requirements

- Python 3.11 or newer.
- A Telegram bot token from [@BotFather](https://t.me/BotFather).
- A running LLM server exposing `POST /v1/chat/completions` with streaming support.
- Optional [audiodoc](https://github.com/WhlteAdmln/audiodoc) service for audio transcription and document text extraction. The bot's `WHISPER_*` and `DOCUMENT_*` setting names are historical; both groups connect to audiodoc.
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
# Windows: .venv\Scripts\activate

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
| `LLM_BASE_URL` | `http://127.0.0.1:8080/v1` | Base URL of the OpenAI-compatible LLM API (the `/v1` prefix is included). |
| `LLM_API_KEY` | `not-needed` | Optional Bearer token for the LLM server; no authorization header is sent for an empty value or `not-needed`. |
| `LLM_MODEL` | `local-model` | Model name sent to the server. |
| `LLM_TEMPERATURE` | `0.7` | Generation temperature; must be non-negative. |
| `LLM_TOP_P` | `0.9` | Sampling parameter from 0 to 1. |
| `LLM_MAX_TOKENS` | `2048` | Maximum number of generated tokens. |
| `LLM_TIMEOUT` | `300` | LLM request timeout in seconds. |
| `LLM_CONTEXT_SIZE` | empty | Context window size in tokens. Set it explicitly when the server does not expose usable context metadata; the standard OpenAI API does not define a context-length field. |
| `LLM_TOKEN_COUNTING` | `auto` | Token counting mode: `auto` probes the llama.cpp `/tokenize` extension once and falls back to an estimate; `llamacpp` requires llama.cpp tokenization endpoints; `estimate` never calls them. |
| `LLM_MAX_CONCURRENT_GENERATIONS` | `1` | Maximum concurrent LLM generations. |
| `MAX_HISTORY_EXCHANGES` | `1000` | Maximum history limit administrators can assign. A normal user's default limit is 30 exchanges. |
| `MAX_STORED_EXCHANGES` | `2000` | Maximum number of full user/assistant exchanges retained per user (up to 4,000 message rows). Older rows and their managed images are pruned after a successful response. |
| `WHISPER_API_URL` | empty | Optional audiodoc transcription endpoint. Set the full URL including `/transcribe`; audio processing is unavailable when unset. |
| `WHISPER_API_KEY` | empty | Optional Bearer token sent to audiodoc for transcription. |
| `WHISPER_TIMEOUT` | `180` | Whisper request timeout in seconds. |
| `DOCUMENT_API_URL` | empty | Optional audiodoc document endpoint. Set the full URL including `/process-document`; document processing is unavailable when unset. |
| `DOCUMENT_API_KEY` | empty | Optional Bearer token sent to audiodoc for document processing. |
| `DOCUMENT_TIMEOUT` | `300` | Document Engine request timeout in seconds. |

Some important limits are code constants rather than environment settings:

- `DEFAULT_HISTORY_EXCHANGES = 30` — normal user's default history limit.
- `MAX_CONTEXT_EXCHANGES = 100` — hard cap on the number of exchanges loaded for one LLM request, regardless of the user's larger saved history limit.
- `MAX_INPUT_TEXT_LENGTH = 12,288` characters — final input text validation limit.
- Incoming Telegram media: 20 MiB maximum per file and at most 3 simultaneous downloads.
- `MAX_AUDIO_DURATION = 300` seconds (5 minutes) for incoming audio, defined in `bot/services/audio/validation.py`.

`MAX_HISTORY_EXCHANGES`, `MAX_CONTEXT_EXCHANGES`, and `MAX_STORED_EXCHANGES` serve different purposes: user-configurable history limit, per-request context cap, and long-term storage cap, respectively.

### LLM server compatibility

| Server capability | Configuration and behavior |
|---|---|
| llama.cpp server | Full compatibility. In `auto` mode the bot detects `/tokenize` and uses exact token counts; `/props` can provide the context size. |
| Other OpenAI-compatible servers | Use `LLM_TOKEN_COUNTING=estimate` (or `auto`, which falls back to estimation when `/tokenize` is unavailable) and set `LLM_CONTEXT_SIZE` to the model's actual context window. `/v1/models` metadata is inspected on a best-effort basis, but context metadata is not part of the standard OpenAI API. |
| Minimum chat API | `POST /v1/chat/completions` with `stream=true`. For the `/health` command, the bot first tries `/health` and then falls back to `GET /v1/models`. |

Do not set `LLM_TOKEN_COUNTING=llamacpp` for a server that does not implement the llama.cpp `/tokenize` and `/apply-template` extensions. The estimated token count is approximate; the bot adds a larger context safety margin in this mode.

Supported document formats are determined by audiodoc. See the [audiodoc README](https://github.com/WhlteAdmln/audiodoc) for its current format list.

## Connecting to audiodoc

This guide connects `bot-obormot` to `audiodoc`. The bot sends audio and documents to audiodoc over HTTP; text chat goes directly from the bot to the OpenAI-compatible LLM server. Image, GIF, sticker, and video handling remains in the bot.

Full setup guide in the audiodoc repository: [Connecting the Telegram bot to audiodoc](https://github.com/WhlteAdmln/audiodoc/blob/main/docs/connecting-the-bot.md).

### 1. Components and request flow

```text
Telegram
   |
   v
bot-obormot (machine A)
   |-- text ------------------------> LLM server: POST /v1/chat/completions
   |-- voice/audio, multipart file -> audiodoc: POST /transcribe
   |-- document, multipart file ----> audiodoc: POST /process-document
   |
   +-- conversation history -------> local SQLite

Machine B normally hosts both audiodoc and the LLM server.
```

The bot must be able to reach the full endpoint URLs. It does not append `/transcribe` or `/process-document` automatically.

### 2. Settings correspondence

| Purpose | `bot-obormot` | `audiodoc` | Notes |
|---|---|---|---|
| Transcription URL | `WHISPER_API_URL` | Uvicorn host/port | Full URL, including `/transcribe` |
| Document URL | `DOCUMENT_API_URL` | Uvicorn host/port | Full URL, including `/process-document` |
| Transcription key | `WHISPER_API_KEY` | `WHISPER_API_KEY` | Values must match |
| Document key | `DOCUMENT_API_KEY` | `DOCUMENT_API_KEY` | Values must match and differ from the transcription key |
| Key rotation | One active key | Comma-separated accepted keys | Enables overlap during rotation |
| Upload field | `file` | `file` | `multipart/form-data` |
| Transcription response | Reads `text` | `{text, language, duration}` | All three fields are part of the response contract |
| Document response | Validates `format`, `text`, `characters`; handles `truncated` | `{format, text, characters, truncated}` | `truncated=true` is reported to the user as an oversized document |

`GET /health` is unauthenticated. `GET /ready` and `POST /process-document` use `DOCUMENT_API_KEY`; `POST /transcribe` uses `WHISPER_API_KEY`. Keep the two keys different. In production, keep `ALLOW_UNAUTHENTICATED=false`.

### 3. Effective limits

| Limit | Bot | audiodoc | Effective behavior |
|---|---:|---:|---|
| Uploaded file size | 20 MiB | Audio 25 MiB; document 50 MiB | The bot's 20 MiB limit is stricter for both upload types |
| Audio duration | 300 s | 600 s | The bot rejects audio over 5 minutes before sending it |
| Text passed to the LLM | 12,288 characters | Up to 2,000,000 characters by default | The bot asks audiodoc for at most 11,264 characters, reserving 1,024 for labels, filename, and caption |
| Request timeout | Audio 180 s; document 300 s | Document processing deadline 180 s | Queue waiting is also part of the bot's request time; tune for your load |
| Waiting queue | — | 4 waiting transcription jobs; 4 waiting document jobs | A full queue returns `503` with `Retry-After: 30` |
| Active document processing | — | 2 workers | CPU, RAM, disk, and OCR cost determine throughput |
| Active transcription | — | 1 worker by default | Whisper can compete with the LLM for CPU/GPU resources |

The bot sends the document `max_characters=11264` multipart field. This reduces extraction work on audiodoc and leaves room for the bot's document label, filename, and an optional Telegram caption. Do not raise this value beyond the bot's input limit without changing and testing the bot's own validation.

### 4. Choose a network layout

#### Scenario 1 — both services on one machine

This is the simplest setup for a local test. Run audiodoc, the LLM server, and the bot on the same host.

`audiodoc/.env`:

```ini
WHISPER_API_KEY=REPLACE_WITH_RANDOM_KEY_1
DOCUMENT_API_KEY=REPLACE_WITH_RANDOM_KEY_2
ALLOW_UNAUTHENTICATED=false
```

Start audiodoc from its project root:

```bash
uvicorn app:app --host 127.0.0.1 --port 8000
```

`bot-obormot/.env`:

```ini
LLM_BASE_URL=http://127.0.0.1:8080/v1
WHISPER_API_URL=http://127.0.0.1:8000/transcribe
WHISPER_API_KEY=REPLACE_WITH_RANDOM_KEY_1
DOCUMENT_API_URL=http://127.0.0.1:8000/process-document
DOCUMENT_API_KEY=REPLACE_WITH_RANDOM_KEY_2
```

Replace the two key placeholders with different random values. The corresponding values in the bot and audiodoc must match.

#### Scenario 2 — two machines over WireGuard (recommended layout)

The deployment examples use machine A (bot) at `10.8.0.2` and machine B (audiodoc plus LLM) at `10.8.0.1`. These are examples; replace them if your WireGuard addresses differ.

On machine B, bind audiodoc to its private VPN address:

```bash
uvicorn app:app --host 10.8.0.1 --port 8000
```

Allow inbound TCP ports `8000` (audiodoc) and `8080` (LLM) only from the bot's VPN address `10.8.0.2`. Review [`deploy/README.md`](https://github.com/WhlteAdmln/audiodoc/blob/main/deploy/README.md) and `deploy/ufw-rules.sh.example` before applying firewall changes. Do not expose either service to the public internet.

`bot-obormot/.env` on machine A:

```ini
LLM_BASE_URL=http://10.8.0.1:8080/v1
WHISPER_API_URL=http://10.8.0.1:8000/transcribe
WHISPER_API_KEY=REPLACE_WITH_RANDOM_KEY_1
DOCUMENT_API_URL=http://10.8.0.1:8000/process-document
DOCUMENT_API_KEY=REPLACE_WITH_RANDOM_KEY_2
```

Use the same two key values in `audiodoc/.env` on machine B. Plain HTTP inside WireGuard is acceptable because the VPN tunnel encrypts traffic between the peers.

#### Scenario 3 — HTTPS through nginx instead of WireGuard

Keep Uvicorn bound to loopback on machine B and let nginx terminate TLS. Configure the nginx source-IP allow-list for the bot host and use a certificate trusted by the bot's operating system/Python environment.

```ini
WHISPER_API_URL=https://backend.example.internal/transcribe
DOCUMENT_API_URL=https://backend.example.internal/process-document
```

Keep the same matching Bearer keys as configured in audiodoc. Do not disable certificate verification in the bot. The LLM server must also use a protected channel or private network; do not expose it directly to the internet.

#### Resource note

The LLM and Whisper can compete for CPU, RAM, and GPU memory when they share machine B. audiodoc defaults to CPU inference (`WHISPER_DEVICE=cpu`). If you move Whisper to a GPU, account for the LLM's VRAM needs and tune the systemd resource controls in the deployment example.

### 5. Verify the connection

Run these commands from machine A (the bot host), not only from machine B. That verifies routing and firewall rules as well as the services. The examples below assume the WireGuard scenario; replace the host for your layout.

Set keys in the current shell for the test session. Do not paste real keys into tickets, logs, or shared terminal recordings:

```bash
export DOCUMENT_API_KEY='your-document-key'
export WHISPER_API_KEY='your-whisper-key'
```

1. Liveness, no key required. After the model loads, expect `loaded: true`:

```bash
curl -fsS http://10.8.0.1:8000/health
```

2. Document dependencies, document key required. Expect booleans and installed language codes:

```bash
curl -fsS http://10.8.0.1:8000/ready \
  -H "Authorization: Bearer ${DOCUMENT_API_KEY}"
```

3. Document extraction. Expect `format`, `text`, `characters`, and `truncated`:

```bash
echo 'Example document text.' > /tmp/audiodoc-sample.txt
curl -fsS \
  -H "Authorization: Bearer ${DOCUMENT_API_KEY}" \
  -F "file=@/tmp/audiodoc-sample.txt" \
  -F "max_characters=11264" \
  http://10.8.0.1:8000/process-document
```

4. Transcription. Use a short valid `.ogg` file and expect `text`, `language`, and `duration`:

```bash
curl -fsS \
  -H "Authorization: Bearer ${WHISPER_API_KEY}" \
  -F "file=@voice.ogg" \
  http://10.8.0.1:8000/transcribe
```

Finally, send a short voice message and a small `.txt` document to the Telegram bot. Successful direct `curl` requests do not replace this end-to-end check.

### 6. Rotate keys without an authentication gap

The audiodoc API accepts multiple comma-separated active keys. Rotate each endpoint key independently:

1. In `audiodoc/.env`, set the endpoint key to `OLD_KEY,NEW_KEY`, then restart audiodoc. Both keys are accepted during the transition.
2. Update the matching key in the bot's `.env`, then restart the bot.
3. After confirming requests succeed, remove `OLD_KEY` from audiodoc's `.env` and restart audiodoc again.

Do not combine the Whisper and document keys; they protect different endpoints.

### 7. Troubleshooting

| Symptom | Likely cause | What to check |
|---|---|---|
| Bot cannot connect to the service | Wrong host/port, service stopped, firewall blocks traffic, or Uvicorn listens only on loopback | Call `/health` from machine A; inspect `ss -tlnp` and UFW rules on B |
| HTTP `404` | URL is missing the endpoint path | Include `/transcribe` or `/process-document` in the bot URL |
| HTTP `401` | Key mismatch or wrong key group | Compare the bot's Whisper key with `WHISPER_API_KEY`, and its document key with `DOCUMENT_API_KEY` without sharing secret values |
| HTTP `503` | Whisper is not loaded or a bounded queue is full | Check `/health`, service logs, and `Retry-After`; reduce load or tune queue limits carefully |
| HTTP `413` | Upload exceeds the bot or server limit | Check the 20 MiB bot limit and audiodoc's 25/50 MiB endpoint limits |
| HTTP `400` for audio | Audio is invalid or longer than the configured server limit | The bot currently rejects audio over 300 seconds; audiodoc defaults to 600 seconds |
| HTTP `504` or bot timeout | Document deadline or client timeout elapsed; queue wait may contribute | Inspect backend logs and load before increasing timeouts |
| First startup appears slow | Whisper model is being downloaded or loaded | Pre-download a model, set `WHISPER_MODEL_PATH`, and use `WHISPER_OFFLINE=true` when ready |

For endpoint details and status codes, see [the API reference](https://github.com/WhlteAdmln/audiodoc/blob/main/docs/api.md). For host hardening and network setup, see [deployment examples](https://github.com/WhlteAdmln/audiodoc/blob/main/deploy/README.md).

## Run

```bash
python -m bot.main
```

The startup sequence is: set the restrictive process umask, configure logging and secret filtering, configure Pillow limits, validate/log the access mode, validate the Telegram token, connect SQLite and apply schema migrations, start the LLM client, start periodic image cleanup, and begin Telegram polling. Shutdown cancels background cleanup and closes the LLM client, database connection, and Telegram session.

The bot is designed for private chats. Messages from groups/supergroups/channels and events without a known sender are not passed to chat handlers; history and personal prompts are user-scoped rather than chat-scoped.

## Check the LLM server

```bash
curl http://127.0.0.1:8080/v1/models
```

Change `LLM_BASE_URL` if the server uses another address or port. If authentication is enabled on the LLM server, set the corresponding secret in `LLM_API_KEY`. Prefer binding the LLM server to localhost or a trusted private interface; do not expose it directly to the public internet.

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

The `integration` test that requires an external LLM server with a `/tokenize` endpoint is run separately:

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
│   ├── llm/         # LLM server client, context fitting, token counting, streaming
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
