# Security

## Access control

- The bot answers only the supervisor, administrators and users on the static
  allowlist. An empty `ALLOWED_USERS` does not make it public.
- `ALLOW_ALL_USERS=true` opens the bot to every user who is not blocked. Use it
  only on purpose.
- Only the supervisor can add or remove administrators.
- Administrator actions are written to the audit log.

## Secrets

- `.env` is created with mode 600 and the home directory with mode 700.
  `bot-obormot doctor` warns when `.env` is readable by other users.
- `bot-obormot config check` and `doctor` print the names of invalid settings
  but never their values.
- `BOT_TOKEN`, `LLM_API_KEY` and the audiodoc keys must not be committed or
  posted in issues. Rotate a key if it has leaked.
- `bot-obormot init --token TOKEN` puts the token in the shell history. Edit the file
  instead when that matters.

## Network

- Connect to audiodoc over a private network (loopback, WireGuard or HTTPS).
  Do not send API keys over plain HTTP across the internet.
- The LLM server should not be reachable from the internet.

## Installation

- The installer downloads only GitHub Release assets and verifies their SHA-256
  checksums before installing.
- Docker: the container runs as an unprivileged user with a read-only root file
  system and no extra capabilities (`compose.yaml`).
- systemd: `bot-obormot service install --system` adds a service account and a
  file system sandbox. The user unit runs with your own account.

## Stored data

The SQLite database holds the conversation history and user settings. Users can
delete their own data with `/forget_me`. Downloaded images are stored in the
`images` directory next to the database and are removed with the history.

## Reporting a vulnerability

See [SECURITY.md](../SECURITY.md).
