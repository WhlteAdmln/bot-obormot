# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- All application errors now derive from a single `AppError` with a `code` and a `public_message`.
- `bot/errors/whisper.py` is now `bot/errors/audiodoc.py` with `Audiodoc*Error` classes.
- The mapping from error `code` to the Russian user text lives only in `bot/services/chat/errors/texts.py`.

### Deprecated

- `BotServiceError` and the `Whisper*Error` names are aliases of `AppError` and `Audiodoc*Error`; they will be removed in the next release.

## [0.1.1] - 2026-11-06

### Added

- Support for OpenAI-compatible LLM servers without llama.cpp-specific endpoints.
- Explicit context-size and token-counting configuration.
- audiodoc document-size negotiation and response truncation handling.
- Contract examples and documentation for connecting audiodoc.

### Fixed

- User-facing text limits now use the configured maximum input length.
- Removed the unused `STREAM_UPDATE_INTERVAL` configuration setting.
