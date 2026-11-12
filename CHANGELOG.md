# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.1] - 2026-11-06

### Added

- Support for OpenAI-compatible LLM servers without llama.cpp-specific endpoints.
- Explicit context-size and token-counting configuration.
- audiodoc document-size negotiation and response truncation handling.
- Contract examples and documentation for connecting audiodoc.

### Fixed

- User-facing text limits now use the configured maximum input length.
- Removed the unused `STREAM_UPDATE_INTERVAL` configuration setting.
