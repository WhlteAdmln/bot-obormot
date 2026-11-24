# Roadmap

This file holds the plans for bot-obormot. It lives next to `CHANGELOG.md`: the changelog records what was released, the roadmap records what is planned and what is in progress. `CLAUDE.md` tells Claude how to read it.

## How to use this file

- Work is split into tasks. One task is one Claude Code session. A task is a heading `#### <ID> <title>` followed by `Needs:`, `Scope:` and `Done when:`.
- IDs are `BO-<number>` for bot-obormot and `AD-<number>` for audiodoc. Numbers are never reused.
- The next task is the first one, in document order, that is not struck through and whose `Needs:` tasks are done. Tasks run in the order of this file.
- A finished task stays in place: its heading and every `Scope:` bullet are struck through (`~~text~~`).
- A task marked `[shared]` changes files that exist in both repositories. audiodoc is the source of truth: the task is done in a session in the audiodoc repository, which edits both working trees. Here it is only a pointer with the same title; it is struck through together with the audiodoc task. Do not start a pointer from this repository.
- Work that is not split into tasks yet lives under "Planned" and "Backlog". It becomes tasks when its release starts.
- When a release is published, its section collapses into one line under "Released".

## Planned

### 0.4.x: alpha finishing

- One assert per test and a message on every assert in all tests, not only the security tests.
- Unusual inputs instead of `"x"` and `"foo"` in all tests.
- Remove the pylint `no-docstring-rgx` exemption for tests and the `D1` ignore for `tests/*`.
- Review the remaining production suppressions: `too-many-instance-attributes` in `config/model/schema.py`, `services/chat/streaming/responder.py` and `services/chat/input/models.py`; `protected-access` in `services/database/decorators.py`; `consider-ternary-expression` in `document_part.py` and `audio_part.py`.
- `FakeLLMOptions` in `tests/support/fake_llm.py` without its `too-many-instance-attributes` suppression.

### 0.5.0: beta

The scope is not defined yet.

## Backlog

- `tests/unit/project/test_env_example.py` keeps its own `_settings_environment_names` helper, a copy of `settings_environment_names` in `scripts/docs_checks/settings.py`; use the public function instead.
- Type LLM chat messages and content parts (`TypedDict` for a message, a text part and an `image_url` part) instead of `dict[str, Any]`; most of the remaining `Any` uses are these dictionaries in `services/llm/`, `services/media/content.py`, `services/chat/input/user_content.py` and `services/database/usecases/history.py` and `facade/history.py`.
- Type the Document Engine response (`text`, `format`, `characters`, optional `truncated`) instead of `dict[str, Any]` in `services/documents/response.py`, `client.py` and `services/chat/input/document_part.py`.
- FSM updates in the `start`, `prompt` and `fallback` handlers and in the temporary-messages middleware build a `dict[str, Any]` only to unpack it into `state.update_data(**data)`, whose `**kwargs` are `Any`; passing the mapping as the first argument would allow `dict[str, int]`, but the test fakes accept keyword arguments only.
- Keyword arguments for `message.answer` in `services/chat/streaming/sending.py` and `responder.py` are `dict[str, Any]`; a `TypedDict` with `Unpack` or explicit arguments would type them.
- `Any` stays where a library signature requires it: `MiddlewareData` and `NextHandler` in `middlewares/aliases.py` follow aiogram's `BaseMiddleware`, and `Coroutine[Any, Any, _R]` in `services/database/decorators.py` is the usual form for a coroutine function.
- Many tests still hold several asserts without a failure message (for example `tests/unit/test_doctor.py`, `tests/unit/services/database/facade/test_access.py`); split them into one assert per test with a message.
- The Telegram download semaphore `_download_slots` in `services/telegram/downloader.py` is created at import and binds to the first event loop in which a download has to wait; a download that waits in another event loop of the same process fails with `RuntimeError` (seen in the unit tests, which use one loop per test). This is implicit global state. Agreed solution: create the semaphore per running bot, for example in the dispatcher setup, and pass it to the downloader.
- `validate_document_response` accepts a boolean (`True`) or a negative `characters` count, because `bool` is a subclass of `int`. The count only goes into a log line, but a nonsensical value means a broken or incompatible audiodoc response. Agreed solution: reject a boolean or negative count as an invalid character count (HTTP 502), the same way the `truncated` flag accepts only a boolean.
- An audiodoc error body longer than `MAX_ERROR_BODY_BYTES` is dropped completely, so the error message ends after the status code with no detail. Agreed solution: keep minimal information about the event, that is the first `MAX_ERROR_BODY_BYTES` bytes of the body, marked as truncated, so the error still names what happened.
- `SecretsFilter` in the shared `log_filters.py` finds a Telegram token by pattern only when a word boundary surrounds it, so it misses the most common form, `bot<token>` inside a Telegram API URL, and a token that ends with `-` or `_` before a `/`. Today the configured `BOT_TOKEN` is still redacted because `configure_logging` passes it as a secret, but a token that is not configured (for example another bot's) stays in the log. Proposed solution: replace `\b` with lookarounds that only exclude digits before and token characters after; a `[shared]` task, changed in audiodoc first.
- Build routers with a factory instead of module-level objects, so tests need no `detach_router` and no `protected-access` suppression (aiogram has no public way to detach a router).

## Released

- 0.3.0 (2026-11-24): deprecated functionality removed, code base aligned with audiodoc, strict lint and test gates. See [CHANGELOG.md](CHANGELOG.md).
- 0.2.2 (2026-11-19): `SYSTEM_PROMPT_PATH` and a fix for answers cut off by `LLM_MAX_TOKENS`. See [CHANGELOG.md](CHANGELOG.md).
