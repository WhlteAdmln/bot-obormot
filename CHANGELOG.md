# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.2.0] - 2026-11-18

### Added

- Command-line interface: `bot-obormot run`, `version`, `init`, `config check`, `doctor` and `service install|uninstall|status`; `python -m bot_obormot` is the same program.
- `BOT_OBORMOT_HOME` (default `~/bot-obormot`) as the application home; `.env` and relative paths such as `DATABASE_PATH` resolve against it.
- Installer with `--version X`, `--nightly`, `--systemd`, `--with-tgs` and a staged, verified `--upgrade` that rolls back on failure and migrates 0.1.x directories (the old source is kept in `.legacy-<version>/`).
- Docker image (multi-stage, unprivileged user, health check) and `compose.yaml`; the image is published to GHCR.
- Optional `tgs` extra for animated stickers; without it the user gets a clear message and one warning is logged.
- Release workflow with wheel, source distribution, `constraints.txt`, `SHA256SUMS` and provenance attestation.
- Documentation: configuration, commands, LLM servers and security guides, plus `make docs-check`.
- CI jobs for integration tests, the installer (including a real 0.1.1 upgrade) and Docker.

### Changed

- The Python package is now `bot_obormot` and the console script is `bot-obormot`.
- All application errors derive from a single `AppError` with a `code` and a `public_message`.
- `bot_obormot/errors/whisper.py` is now `bot_obormot/errors/audiodoc.py` with `Audiodoc*Error` classes.
- The mapping from error `code` to the Russian user text lives only in `bot_obormot/services/chat/errors/texts.py`.
- `Settings` is imported only from `bot_obormot.settings`; settings are created by `load_settings()` and nothing reads the environment at import time.
- The audiodoc settings are `AUDIODOC_URL` (base URL), `AUDIODOC_AUDIO_KEY`, `AUDIODOC_DOCUMENT_KEY`, `AUDIODOC_AUDIO_TIMEOUT` and `AUDIODOC_DOCUMENT_TIMEOUT`.
- `.env` is read from the home directory and then from the working directory; the environment readers are shared with audiodoc.
- The README is shorter; configuration, commands, LLM servers and security moved to `docs/`.

### Deprecated

- `WHISPER_API_URL`, `WHISPER_API_KEY`, `WHISPER_TIMEOUT`, `DOCUMENT_API_URL`, `DOCUMENT_API_KEY` and `DOCUMENT_TIMEOUT` are read only when the new name is empty and log a deprecation warning. They will be removed in 0.3.0.
- `python -m bot.main` still works through a compatibility package, prints a deprecation line and will be removed in 0.3.0.
- `BotServiceError` and the `Whisper*Error` names are aliases of `AppError` and `Audiodoc*Error`; they will be removed in 0.3.0.

### Removed

- The old installer flags `--latest` (latest is now the default) and the installer-managed system package installation; the installer prints the commands instead.
- The source-archive installation; the installer installs the release wheel.

## [0.1.1] - 2026-11-06

### Added (0.1.1)

- Support for OpenAI-compatible LLM servers without llama.cpp-specific endpoints.
- Explicit context-size and token-counting configuration.
- audiodoc document-size negotiation and response truncation handling.
- Contract examples and documentation for connecting audiodoc.

### Fixed

- User-facing text limits now use the configured maximum input length.
- Removed the unused `STREAM_UPDATE_INTERVAL` configuration setting.
