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

## 0.3.0 (in progress)

Goal: remove deprecated functionality, make the code base uniform with audiodoc and make every gate strict. Behavior does not change except for the removed functionality. The starting point is 0.2.2.

### Tasks

#### BO-01 Suppressions and subprocess calls

- Needs: none.
- Scope:
  - Remove the remaining `noqa` suppressions or give each a one-line reason: `S603` in `bot_obormot/cli.py`, two `S310` in `bot_obormot/doctor.py`, `BLE001` in `bot_obormot/handlers/chat/handler.py`.
  - Run subprocesses through one wrapper with a validated argv and `shutil.which`.
  - Add a comment to the `DEP002` entry `rlottie-python` in `pyproject.toml`.
- Done when: no `noqa` without a reason; `make check` is green.

#### BO-02 Precise types instead of `Any`

- Needs: none.
- Scope:
  - Replace `Any` where the precise type is obvious (73 uses left in `bot_obormot/`); leave the others as they are and list the groups that need a design decision.
- Done when: mypy strict passes, behavior is unchanged, `make check` is green.

#### BO-03 `UserLocks`

- Needs: none.
- Scope:
  - Replace the module-level dictionary in `bot_obormot/services/chat/locks.py` with an explicit `UserLocks` object that has `__len__`; the application creates it and passes it down.
  - Tests check that no entry leaks after a request, including after an error.
- Done when: no module-level mutable state is left in the locks module; `make check` is green.

#### BO-04 Split `markdown_v2.py` and `database/facade.py`

- Needs: none.
- Scope:
  - Split `bot_obormot/services/chat/formatting/markdown_v2.py` (451 lines) and `bot_obormot/services/database/facade.py` (386 lines) by responsibility.
  - Remove the `consider-ternary-expression` suppression in `markdown_v2.py` if the split makes it unnecessary.
  - Move the tests so that every module has one mirrored test file.
- Done when: the import-linter contracts stay valid, `make check` is green.

#### BO-05 Split `admin/handler.py` and `config/model.py`

- Needs: none.
- Scope:
  - Split `bot_obormot/handlers/admin/handler.py` (355 lines) and `bot_obormot/config/model.py` (334 lines) by responsibility.
  - Move the tests so that every module has one mirrored test file.
- Done when: as BO-04. If a split is not clean, list the file in the answer and in `ROADMAP.md`.

#### ~~BO-06 [shared] Split `scripts/check_docs.py` and document its differences~~

- Needs: none.
- Scope:
  - ~~Pointer to AD-03. Done in the audiodoc session; do not start from here.~~
- Done when: AD-03 is done.

#### ~~BO-07 [shared] `make check` runs every CI gate; one extra for test dependencies~~

- Needs: none.
- Scope:
  - ~~Pointer to AD-04. Done in the audiodoc session; do not start from here.~~
- Done when: AD-04 is done.

#### BO-08 Replace mocks with fakes

- Needs: none.
- Scope:
  - Replace every `unittest.mock`, `MagicMock`, `AsyncMock` and `assert_called*` (46 uses) with fakes in `tests/support/`, one per external collaborator (Whisper client, LLM, aiohttp, Telegram, database, ffmpeg).
  - Test count does not fall; coverage does not drop.
- Done when: a scan finds no mock; `make check` is green.

#### BO-09 General test rules in bot-obormot

- Needs: BO-06, BO-08.
- Scope:
  - Remove comments from test files (38 left, except tool pragmas with a reason), docstrings from test functions, classes defined inside test functions (for example in `tests/unit/handlers/start/test_handler.py`), `time.sleep` for waiting and temporary files outside `tmp_path`.
  - Remove private access in tests (`detach_router` stays until the router factory in "Backlog").
  - Review the `dispatcher` fixture in `tests/support/dispatcher_fixtures.py` for shared mutable state and fixtures wider than `function` scope.
  - Rename tests whose names are not sentences with a verb, and mechanical names such as `expected_fragment` or `expected_text_2`.
- Done when: a throwaway scan finds none of the above; the test count did not fall; `make check` is green.

#### BO-10 [shared] `scripts/check_test_rules.py`

- Needs: none.
- Scope:
  - Pointer to AD-06. Done in the audiodoc session; do not start from here.
- Done when: AD-06 is done.

#### BO-11 Security tests: access control and administration

- Needs: BO-10.
- Scope:
  - Bring these files to the full standard: one assert per test, a message on every assert, hostile and unusual inputs, public entry points only, and add them to the list of `check_test_rules.py`.
  - `tests/unit/middlewares/`: `test_access.py`, `test_throttle.py`, `test_correlation_id.py`.
  - `tests/unit/services/access/test_service.py`, `tests/unit/handlers/admin/test_handler.py`, `tests/unit/services/database/repositories/test_admins.py`.
- Done when: the script passes with these files on the list; coverage did not drop.

#### BO-12 Security tests: limits, validation, audiodoc clients, Telegram input

- Needs: BO-10.
- Scope:
  - Same standard as BO-11 for `tests/unit/common/` (`test_http_limits.py`, `test_validation.py`, `test_text.py`), `tests/unit/services/audio/` (`test_validation.py`, `test_client.py`), `tests/unit/services/documents/` (`test_client.py`, `test_response.py`), `tests/unit/services/telegram/test_downloader.py`, `tests/unit/services/chat/test_incoming_log.py`, `tests/unit/services/llm/test_messages.py` (prompt-injection markers).
- Done when: as BO-11.

#### BO-13 Security tests: media, log filters, installer

- Needs: BO-10.
- Scope:
  - Same standard as BO-11 for `tests/unit/services/media/` (`test_sniff.py`, `test_safety.py`, `test_limited.py`, `animation/test_tgs.py`, `animation/test_video.py`), `tests/unit/test_log_filters.py` and `tests/unit/project/test_installer.py`.
  - Review the whole test tree once more against the security criteria (limits, authentication and permissions, dangerous files, masking of secrets and logs, subprocesses, installation) and add files that qualify.
- Done when: as BO-11.

#### BO-14 [shared] Release 0.3.0

- Needs: none.
- Scope:
  - Pointer to AD-10. Done in the audiodoc session; do not start from here.
- Done when: AD-10 is done.

### Done before this roadmap

- ~~The `WHISPER_*` and `DOCUMENT_*` settings are removed; the `AUDIODOC_*` settings replace them.~~
- ~~The `bot` package, `python -m bot.main`, the deprecated error aliases `BotServiceError` and `Whisper*Error` and the `MAX_HISTORY_IMAGES` alias are removed.~~
- ~~The compatibility dispatcher in `services/media/animation` and the re-exports in `handlers.chat` and `handlers.history` are removed.~~
- ~~The 0.1.x upgrade path in `install.sh`, its CI job and the old-schema database fixture are removed.~~
- ~~pylint with every message and all stable extensions, pinned to 4.1.4, rated 10.00 for the package, the scripts and every test module.~~
- ~~Renovate replaces Dependabot version updates; the lock is refreshed monthly and merged by a human.~~
- ~~`make lock` generates `requirements-lock.txt` with `uv`; `scripts/check_lock.py` checks it.~~
- ~~CI test matrix and classifiers cover Python 3.11 to 3.14; the unit suite passes on Python 3.14 with the lock and every compiled dependency has a 3.14 wheel (checked on PyPI; `rlottie-python` ships an `abi3` wheel).~~
- ~~`AGENTS.md`, `scripts/check_vendored.py` (15 files), `scripts/check_test_layout.py`, `scripts/check_changelog.py` and `scripts/coverage_gaps.py`, shared with audiodoc; the CI job with the latest dependencies installs `defusedxml`.~~
- ~~vulture runs without a whitelist; the ruff ignores `FBT`, `TD002`, `TD003`, `FIX002` are gone and the test ignores are reduced to `S101` and `D1`.~~
- ~~Magic values are named constants, every `try` wraps one statement, long functions are split; `build_parser` is public.~~
- ~~The audiodoc clients share `services/audiodoc_http.py`; media decoding and image preparation share `services/media/limited.py`; `services.database` re-exports helpers from the modules that define them; the private `LLMClient` methods used only by tests are removed.~~
- ~~The missing `[tgs]` extra is reported once at startup and by `doctor`; `handlers/prompt/texts.py` needs no `line-too-long` suppression.~~
- ~~Unit tests mirror the production unit they cover; one shared fake per collaborator in `tests/support/`; long tests are split (940 to 993 tests).~~
- ~~`AccessDatabase` is split into state, `CallLog` and `DatabaseScenario`; checks for an empty result compare with a typed empty literal.~~

## Planned

### 0.4.x: alpha finishing

- One assert per test and a message on every assert in all tests, not only the security tests.
- Unusual inputs instead of `"x"` and `"foo"` in all tests.
- Remove the pylint `no-docstring-rgx` exemption for tests and the `D1` ignore for `tests/*`.
- Review the remaining production suppressions: `too-many-instance-attributes` in `config/model.py`, `services/chat/streaming/responder.py` and `services/chat/input/models.py`; `too-many-public-methods` in `services/database/facade.py`; `protected-access` in `services/database/decorators.py`; `consider-ternary-expression` in `document_part.py` and `audio_part.py`.
- `FakeLLMOptions` in `tests/support/fake_llm.py` without its `too-many-instance-attributes` suppression.

### 0.5.0: beta

The scope is not defined yet.

## Backlog

- `tests/unit/project/test_env_example.py` keeps its own `_settings_environment_names` helper, a copy of `settings_environment_names` in `scripts/docs_checks/settings.py`; use the public function instead.
- Build routers with a factory instead of module-level objects, so tests need no `detach_router` and no `protected-access` suppression (aiogram has no public way to detach a router).

## Released

- 0.2.2 (2026-11-19): `SYSTEM_PROMPT_PATH` and a fix for answers cut off by `LLM_MAX_TOKENS`. See [CHANGELOG.md](CHANGELOG.md).
