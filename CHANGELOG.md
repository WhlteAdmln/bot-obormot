# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- [#142](https://github.com/WhlteAdmln/bot-obormot/issues/142) `scripts/check_vendored.py` also compares the shared `tests/unit/scripts/docs_checks/test_settings.py`.
- [#116](https://github.com/WhlteAdmln/bot-obormot/issues/116) `scripts/check_vendored.py` also compares the shared `docs_checks` modules `links.py`, `markdown.py`, `russian.py` and their tests.
- [#131](https://github.com/WhlteAdmln/bot-obormot/issues/131) `scripts/check_vendored.py` has its own shared unit tests in `tests/unit/scripts/test_check_vendored.py`.
- [#130](https://github.com/WhlteAdmln/bot-obormot/issues/130) CI reports the number of changed lines of a pull request against the 256-line limit without failing.
- [#129](https://github.com/WhlteAdmln/bot-obormot/issues/129) Contributors can read the shared development principles in `docs/development-principles.md` and its Russian twin.

### Fixed

- [#112](https://github.com/WhlteAdmln/bot-obormot/issues/112) Each bot gets its own Telegram download limit, so a download that waits for a free slot in a new event loop no longer fails with `RuntimeError`.
- [#114](https://github.com/WhlteAdmln/bot-obormot/issues/114) An error message from the Document Engine or the transcription service keeps the start of a long error body, marked as truncated.
- [#113](https://github.com/WhlteAdmln/bot-obormot/issues/113) A Document Engine response with a boolean or negative character count is rejected as invalid.
- [#115](https://github.com/WhlteAdmln/bot-obormot/issues/115) Logs redact a Telegram token inside a bot API URL or one that ends with `-`.

## [0.3.0] - 2026-11-24

Deprecated functionality is not supported starting with 0.3.0.

### Added

- pylint with every message enabled and all stable extensions (pinned to 4.1.4), next to ruff and mypy, for the package, the scripts and every test module.
- `AGENTS.md` and `CLAUDE.md` with the rules for LLM agents, and `ROADMAP.md` with the planned work; `CONTRIBUTING.md` links them.
- Checks shared with audiodoc: `scripts/check_test_layout.py` (unit tests mirror the production unit they cover), `scripts/check_test_rules.py` (no mocks, no classes inside test functions, no `tempfile` or `time.sleep`, no comments in tests; strict files need one assert with a message per test), `scripts/check_changelog.py` (section order) and `scripts/coverage_gaps.py`.
- `make lock` generates `requirements-lock.txt` with `uv pip compile` and skips releases younger than 14 days unless `LOCK_MIN_RELEASE_AGE_DAYS=0` is passed.
- `make check` runs every local CI gate, including `pip check`, `make audit`, `make test-no-skips` and `make release-check`.
- The `test` extra holds the test dependencies; the `dev` extra includes it.
- `bot_obormot/common/process.py` is the one place that starts external programs: `run_program` rejects a program name that is a path or an option and NUL bytes in the argv, resolves the program with `shutil.which` and runs it without a shell.
- Python 3.14 classifiers and a Python 3.14 CI job.

### Changed

- Renovate replaces Dependabot version updates. It refreshes the lock monthly, updates coupled packages together and leaves major, `0.x`, GitHub Actions, pre-commit, build tooling and parser or network minor updates to a human. Dependabot alerts stay enabled.
- `bot-obormot service status`, ffprobe and ffmpeg run through `run_program`; ffprobe and ffmpeg start by their resolved absolute path instead of through `/usr/bin/env`, and a missing one is reported as `<name> was not found on this system.`
- The warning about the missing `[tgs]` extra is logged once at startup instead of by the first animated sticker; `bot-obormot doctor` still reports it.
- Per-user chat locks live in a `UserLocks` object created by `bootstrap.main` instead of a module-level dictionary.
- Large modules are packages split by responsibility: `services/chat/formatting/markdown_v2`, `services/database/facade`, `handlers/admin/handler` and `config/model`. Public import paths are kept, except that `bot_obormot.config.model` and `bot_obormot.services.database.facade` no longer re-export names: import them from `bot_obormot.settings` and `bot_obormot.services.database`. Behavior is unchanged.
- The audiodoc clients share `services/audiodoc_http.py`; media decoding and image preparation share `services/media/limited.py`.
- `scripts/check_docs.py` is split into `scripts/docs_checks/`; `CONTRIBUTING.md` describes how the copies in both repositories differ. `build_parser` in the CLI module is public.
- Stricter lint: `max-try-statements = 1`, magic values as named constants, long functions split, no vulture whitelist, precise types instead of obvious `Any`, and the ruff ignores `FBT`, `TD002`, `TD003`, `FIX002`, `ANN`, `ARG`, `PLR2004` and `SLF001` are gone. Behavior is unchanged.
- CI tests Python 3.14; the job with the latest allowed dependencies installs the `test` extra.
- Tests follow the general test rules: one file per production unit, one fake per collaborator in `tests/support/` instead of `unittest.mock`, function-scoped fixtures, typed empty literals, no sleeping. Test functions and modules still need no docstring; a later release removes this exemption.
- The security tests of access control, administration, size limits, input validation, the audiodoc clients, Telegram input, media, log redaction, the program runner, `.env`, systemd and the installer have one assert with a message per test, cover hostile inputs and are listed in `tests/strict_test_files.txt`.

### Fixed

- The CI job that tests with the latest allowed dependencies installs `defusedxml`, which `scripts/coverage_gaps.py` imports.

### Removed

- The `WHISPER_API_URL`, `WHISPER_API_KEY`, `WHISPER_TIMEOUT`, `DOCUMENT_API_URL`, `DOCUMENT_API_KEY` and `DOCUMENT_TIMEOUT` settings. Use the `AUDIODOC_*` settings.
- The `bot` package and `python -m bot.main`. Use `bot-obormot` or `python -m bot_obormot`.
- The deprecated error aliases `BotServiceError` and `Whisper*Error`. Use `AppError` and `Audiodoc*Error`.
- The `MAX_HISTORY_IMAGES` alias. Use `MAX_HISTORY_MEDIA_MESSAGES`.
- The compatibility dispatcher in `services/media/animation` and the re-exports in the `handlers.chat` and `handlers.history` packages.
- The private `LLMClient` static methods used only by tests; the public `normalize_messages`, `prepare_messages_for_count` and `count_images` remain.
- The unused `bot_obormot/services/chat/formatting/roleplay.py`.
- The 0.1.x migration in `install.sh`, its CI job and the old-schema database fixture.

## [0.2.2] - 2026-11-19

### Added (0.2.2)

- `SYSTEM_PROMPT_PATH` setting: an optional UTF-8 file that replaces the built-in default system prompt, so the administrator can rewrite it without the length limit of personal prompts. A relative path resolves against the home directory, the file is read at startup, and an unusable file is reported as a configuration error (also by `bot-obormot doctor`).

### Fixed (0.2.2)

- A response that a reasoning model cut off at `LLM_MAX_TOKENS` before it wrote any answer no longer ends with a traceback and an "unexpected error" message. The bot now says that the model used the whole token limit, logs a warning that suggests raising `LLM_MAX_TOKENS`, and also warns when a non-empty answer is truncated by the limit. An empty answer in general raises the dedicated `LLMEmptyResponseError` instead of `RuntimeError`.

## [0.2.1] - 2026-11-19

### Added (0.2.1)

- The bot answers with a visual reply: the response is sent with `reply_parameters` pointing to the user's message. `chat_id` and `message_id` are stored per request, so the link stays correct when several messages arrive in a row and LLM responses finish in a different order. When several messages are combined into one request, the response is linked to the last of them. `allow_sending_without_reply` keeps the response deliverable if the original message is gone. For a long response only the first part is a reply.
- Automatic detection of the response format: Markdown is sent with `parse_mode=MarkdownV2`, Telegram HTML with `parse_mode=HTML`, plain text without `parse_mode`. Mixed or ambiguous text (for example Markdown together with HTML tags, or unbalanced tags) is sent as plain text. Code is ignored when the format is detected, and no configuration is needed.
- Conversion of Markdown to MarkdownV2 (bold, italic, strikethrough, code, links, quotes, lists, headings, tables as code blocks) with the required escaping, and sanitizing of HTML to the tags and attributes that Telegram supports.
- Safe fallback: when Telegram rejects the formatting with a parse error, the message is sent once more without `parse_mode`, using the original LLM text and the same `reply_parameters`. If the retry fails, the error is logged.

### Changed (0.2.1)

- The text is shown without formatting while the response is being generated; the format is detected once, when the final message is delivered.
- Long responses are split before conversion, at block boundaries; a fenced code block that has to be split is closed and reopened in every part.
- The roleplay markup is replaced with standard Markdown: `*text*` and `**text**` keep working as italic and bold, while `~text~` is no longer a quote block.
- Network errors and requests with an unknown delivery status are never retried: a failed delivery of the final response is no longer sent again after a network error, and a failure while sending a later part no longer repeats the parts that were already delivered.

### Fixed (0.2.1)

- `install.sh --upgrade` no longer leaves the paths of the staged `.venv.new` in the activated environment: the shebang of `bot-obormot`, the `activate` scripts and `pyvenv.cfg` now point to `.venv`, so the systemd unit can start the service after an upgrade. If the paths cannot be updated, the previous environment is restored.

### Removed (0.2.1)

- `format_roleplay`; use `prepare_response` from `bot_obormot.services.chat.formatting`.

## [0.2.0] - 2026-11-18

### Added (0.2.0)

- Command-line interface: `bot-obormot run`, `version`, `init`, `config check`, `doctor` and `service install|uninstall|status`; `python -m bot_obormot` is the same program.
- `BOT_OBORMOT_HOME` (default `~/bot-obormot`) as the application home; `.env` and relative paths such as `DATABASE_PATH` resolve against it.
- Installer with `--version X`, `--nightly`, `--systemd`, `--with-tgs` and a staged, verified `--upgrade` that rolls back on failure and migrates 0.1.x directories (the old source is kept in `.legacy-<version>/`).
- Docker image (multi-stage, unprivileged user, health check) and `compose.yaml`; the image is published to GHCR.
- Optional `tgs` extra for animated stickers; without it the user gets a clear message and one warning is logged.
- Release workflow with wheel, source distribution, `constraints.txt`, `SHA256SUMS` and provenance attestation.
- Documentation: configuration, commands, LLM servers and security guides, plus `make docs-check`.
- CI jobs for integration tests, the installer (including a real 0.1.1 upgrade) and Docker.

### Changed (0.2.0)

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

### Removed (0.2.0)

- The old installer flags `--latest` (latest is now the default) and the installer-managed system package installation; the installer prints the commands instead.
- The source-archive installation; the installer installs the release wheel.

## [0.1.1] - 2026-11-06

### Added (0.1.1)

- Support for OpenAI-compatible LLM servers without llama.cpp-specific endpoints.
- Explicit context-size and token-counting configuration.
- audiodoc document-size negotiation and response truncation handling.
- Contract examples and documentation for connecting audiodoc.

### Fixed (0.1.1)

- User-facing text limits now use the configured maximum input length.
- Removed the unused `STREAM_UPDATE_INTERVAL` configuration setting.
