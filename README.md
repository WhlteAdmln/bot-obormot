# bot-obormot

An asynchronous Telegram bot (Python 3.11+, aiogram 3) that gives private-chat
access to a language model through an OpenAI-compatible API. Conversation
history lives in SQLite. Audio and documents can optionally be processed by
[audiodoc](https://github.com/WhlteAdmln/audiodoc).

Russian version: [README.ru.md](README.ru.md).

## Features

- Streaming answers from any OpenAI-compatible server, such as llama.cpp or vLLM.
- Replies to your message, with Markdown and HTML in the answer shown as Telegram formatting.
- Per-user history with adjustable limits and per-user system prompts.
- Images, GIFs, video and animated stickers are handled locally. Animated stickers need the optional `tgs` extra, which the Docker image does not install.
- Voice messages, audio files and documents through audiodoc (optional).
- Supervisor, administrators and an allowlist control who can use the bot.
- `bot-obormot doctor` checks the installation; the installer upgrades it safely.

## Installation

You need Linux with glibc, Python 3.11+ with `venv`, `curl`, `sha256sum` and a bot token from [@BotFather](https://t.me/BotFather). Install `ffmpeg` for video support.

### Installer (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/WhlteAdmln/bot-obormot/main/install.sh | sh
```

The installer downloads the latest GitHub Release wheel, verifies its SHA-256
checksum, creates `~/bot-obormot` with a virtual environment and a protected
`.env`, and never installs system packages. Options go after `-s --`:
`--version X`, `--nightly` (newest prerelease), `--systemd` (user unit, not
started), `--with-tgs` (animated stickers, needs a C compiler and CMake).

```bash
nano ~/bot-obormot/.env                      # set BOT_TOKEN and SUPERVISOR_ID
~/bot-obormot/.venv/bin/bot-obormot doctor   # check the installation
~/bot-obormot/.venv/bin/bot-obormot run      # or: service install, see below
```

To upgrade, run the same command with `-s -- --upgrade`. The upgrade keeps
`.env`, `data/` and the unit, swaps the virtual environment only after a staged
check passes, and rolls back on failure.

### Docker Compose

```bash
cp .env.example .env                 # set BOT_TOKEN and SUPERVISOR_ID
docker compose up -d
```

The image runs as an unprivileged user, keeps data in the `bot_obormot_data`
volume and checks itself with `bot-obormot doctor --offline`. It builds from
`python:3.12-slim` pinned by digest in `Dockerfile`; Renovate proposes digest
updates as pull requests.

### From source

```bash
python3 -m venv .venv && .venv/bin/pip install -c requirements-lock.txt .
.venv/bin/bot-obormot init           # creates ~/bot-obormot/.env
.venv/bin/bot-obormot run
```

To run the bot under systemd, use `bot-obormot service install` (add `--system`
for a system unit). It only writes the unit; you enable and start it yourself.

## Configuration

Settings come from `.env` in `BOT_OBORMOT_HOME` (default `~/bot-obormot`) and the
environment. See [docs/configuration.md](docs/configuration.md) for all of them.

| Setting | Meaning |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token (required) |
| `SUPERVISOR_ID` | Numeric Telegram ID of the owner (required) |
| `ADMIN_IDS`, `ALLOWED_USERS` | Initial administrators and a static allowlist |
| `ALLOW_ALL_USERS` | `true` opens the bot to every user who is not blocked |
| `LLM_BASE_URL`, `LLM_MODEL` | OpenAI-compatible server and model name |
| `LLM_API_KEY` | API key for the LLM server |
| `LLM_CONTEXT_SIZE` | Set it if the server does not report its context size |
| `DATABASE_PATH` | SQLite file, relative to the home directory |
| `AUDIODOC_URL` | Base URL of audiodoc; empty disables audio and documents |

LLM server details are in [docs/llm-servers.md](docs/llm-servers.md).

## Commands

Everyone: `/start`, `/history`, `/history_limit`, `/history_clear`,
`/forget_me`, `/prompt`, `/prompt_set`, `/prompt_reset`, `/cancel`.
Administrators: `/health`, `/ban`, `/unban`. Supervisor: `/admin`, `/admins`,
`/admin_add`, `/admin_remove`. Console commands: `run`, `version`, `init`,
`config check`, `doctor` and `service`. Details are in
[docs/commands.md](docs/commands.md).

## Connecting to audiodoc

1. Install and start audiodoc on a host the bot can reach.
2. In audiodoc, create separate API keys for audio and for documents.
3. Set `AUDIODOC_URL` to the audiodoc base URL, for example
   `http://127.0.0.1:8000`.
4. Set `AUDIODOC_AUDIO_KEY` and `AUDIODOC_DOCUMENT_KEY` to the keys from step 2.
5. Run `bot-obormot doctor`; the audiodoc line should be `OK`.
6. Restart the bot.

Use a private network or HTTPS between the two services. Network layout, key
rotation and troubleshooting are described in audiodoc's
[connecting the bot](https://github.com/WhlteAdmln/audiodoc/blob/main/docs/connecting-the-bot.md)
guide.

## Documentation

- [Configuration](docs/configuration.md) and [commands](docs/commands.md)
- [LLM servers](docs/llm-servers.md) and [security](docs/security.md)
- [Architecture](docs/architecture.md) ([Russian](docs/architecture.ru.md))
- [Contributing](CONTRIBUTING.md), [security policy](SECURITY.md) and
  [changelog](CHANGELOG.md)

MIT license. Run `make install-dev` and `make check` to develop.
