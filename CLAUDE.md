# CLAUDE.md

@AGENTS.md

This file is shared byte for byte by the sibling repositories listed in `scripts/check_vendored.py`. It holds the development standards and says where the work comes from. It names no project: project facts live in `README.md`, `CONTRIBUTING.md`, `pyproject.toml` and `ROADMAP.md`.

## Language

Answer in the language of the user's messages. Code, comments, documentation, `CHANGELOG.md` and `ROADMAP.md` are in English; a document with a `.ru.md` twin is updated in both languages.

## Session start

1. Read `ROADMAP.md`. It is the only source of truth for what is done and what is next. Do not rely on memory or on earlier conversations.
2. Run `git status` and `git log --oneline -5` (read-only). If the working tree has uncommitted changes, tell the user and ask whether they belong to the previous task before touching anything.
3. Find the next task: the first task, in document order, that is not struck through and whose `Needs:` tasks are all done. Tasks of the sibling repository count: read its `ROADMAP.md` (the path is in the shared-files section of `CONTRIBUTING.md`).
4. Propose that task in two or three lines (ID, title, what will change) and wait for the user to confirm. If the user's first message names another task or asks for something else, follow that instead. If every remaining task is blocked by an open `Needs:` task, say which one and in which repository it has to run first.
5. A `[shared]` pointer in the repository that is not the source of truth is never started from there. If it is the next task, tell the user which task to run and that the session has to open in the source-of-truth repository.

One task is one session. Do not start a second task in the same session.

## Working on a task

- A task is a heading `#### <ID> <title>` with `Needs:`, `Scope:` and `Done when:`. Do what `Scope:` says and nothing else (rule 12 of `AGENTS.md`). A related finding goes into `ROADMAP.md` as a new task or a backlog item, not into the diff.
- A task marked `[shared]` changes files that exist in both repositories. It is driven from the source-of-truth repository named in `CONTRIBUTING.md`; the other repository holds a pointer task with the same title. Edit both working trees in one session, then run `scripts/check_vendored.py --other <path>` in both. If the sibling is not reachable, tell the user to restart Claude Code with `--add-dir <path>`.
- Behavior does not change unless the task says so. If a fix would change behavior or a public API, stop and ask one short question, and continue with the rest meanwhile.
- If the task turns out to be larger than one session, finish a clean part, split the remainder into new tasks in `ROADMAP.md` and say so.

## Completing a task

1. Run `make check` (or `make -k check` to see every failure) and `scripts/check_vendored.py --other <path>` in every repository you changed. Every gate must be green. Say which gate could not run on this machine and why; never claim a gate passed without running it.
2. Add entries under `[Unreleased]` in `CHANGELOG.md`, in the section order Added, Changed, Deprecated, Fixed, Removed, Security (`scripts/check_changelog.py` enforces it).
3. Update `ROADMAP.md`: strike through the heading of the finished task and each of its `Scope:` bullets (`~~text~~`), and strike its pointer in the sibling repository. Add newly found work.
4. Tell the user in plain words that the task is finished: `<ID> done`, in the user's language, followed by a short summary: what changed, test count and coverage before and after, gates run, assumptions, anything not verified, and which suppressions the task touched.
5. Name the next task (ID and title) and say that it needs a new session. Do not start it.

## Git and CI

Git and CI belong to the user. Without a request in the current session, do not run any command that writes to the repository or to a remote. When the user asks in the session, create a branch from the current state, `git add`, `git commit`, `git push -u origin <branch>` and open a pull request with `gh pr create`; show the pull request text to the user and wait for approval before creating it. Never force-push, merge, rebase, reset, tag, delete a branch, push to `main` or change a pull request the user did not ask about. Read-only commands (`git status`, `diff`, `log`, `show`) are fine. The user watches CI and merges in the web interface. Commit and pull request text is English; the pull request text follows `.github/pull_request_template.md` and carries no generated-by attribution line: never add `🤖 Generated with [Claude Code](https://claude.com/claude-code)` or a similar line.

## Standards

### General

- Use a mature, maintained library when one is already a dependency or the replacement is clearly smaller and safer; justify a new dependency in the answer.
- Verify facts against primary sources (installed package source, repository files, PyPI, official documentation), not memory.
- Python 3.11 syntax, line length 88. `ruff format` joins lines, so a split literal can come back on one line; `ISC004` requires parentheses around implicit concatenation. A very long line with an invisible character (for example the emoji variation selector) is fixed by writing the character as `️`, not by a suppression.
- Never edit `requirements-lock.txt` by hand; use `make lock`. Do not run `uv pip compile` or `pip freeze` into it.

### Lint, types, coverage

- No new suppression. If one is unavoidable, use the narrowest code and a one-line reason on the same line.
- pylint: no blanket disables; only `# pylint: disable=<code>  # reason` or `# pylint: disable-next=<code>  # reason`. `I0021` (useless suppression) is fatal, and a duplicated pragma also raises it. A pragma counts towards the line length. `I0011` and `I0020` in the output are the normal report of allowed suppressions.
- The `ruff`, `mypy` and `pylint` tables of `pyproject.toml`, including `per-file-ignores`, are shared, so a ruff exception for one repository is only possible as an inline `# noqa`.
- Coverage never drops and `fail_under` is never lowered. A gate that was green does not turn red. The test count does not fall, except for tests of functionality that the task deletes; list them.
- Replace `Any` only where a precise type is obvious.

### Tests

New and changed tests follow these rules even where older tests do not yet; `ROADMAP.md` tracks the gap.

- One test file per production unit, at the mirrored path (`pkg/a/b.py` → `tests/unit/a/test_b.py`; a module with several classes gets one file per class). Tests that target no single module live in `tests/unit/project/` or `tests/unit/scripts/`. `scripts/check_test_layout.py` enforces this. Parametrize instead of expanding into files.
- Test names are sentences that start with a verb (`test_builds_html_page`). No comments (except tool pragmas with a reason) and no docstrings in test functions.
- One assert per test, with a failure message: `assert actual == expected, "what is wrong"`. Compare an empty result with a typed literal (`expected_empty = []`, then `assert value == expected_empty, "message"`), not with truthiness. Inputs are irregular and differ between tests, never `"foo"`. Literals are local variables, not inlined and not module constants.
- No `unittest.mock`, `MagicMock`, `AsyncMock` or `assert_called*`. Fakes live in `tests/support/`, one per external collaborator; no class is defined inside a test function; no inheritance to reuse test tools. `monkeypatch` is for environment variables and unavoidable seams.
- Test through the public interface; no private names, no `SLF001` or `protected-access`. Do not assert on logs unless the unit under test is logging. Do not test getters, setters or constructors.
- No shared mutable state: function-scoped fixtures only, with `@pytest.fixture(name=...)`. Temporary files only in `tmp_path`; never mock the file system; no arbitrary `sleep`. Clean up before a test, not after.
- No `pytest.fail` and no "does not raise" tests. A test that asserts wrong behavior is marked `pytest.mark.skip(reason=...)` and listed in the answer.
- Tests need no network, GPU or real secrets. Integration tests are marked and excluded from the default run. Child processes use `spawn` and import the test module, so keep modules import-safe. Do not add heavy imports to a `conftest.py`.

### Shared files

`scripts/check_vendored.py` holds the list of files that are identical in the sibling repositories and the check that compares them. The source-of-truth repository is named in `CONTRIBUTING.md`: change a shared file there first, copy it to the sibling, and run `check_vendored.py` in both. A new shared file is added to the list in the script, to the shared-files section of `CONTRIBUTING.md` and to the script's test.

### Documentation

`README.md`, `CONTRIBUTING.md`, `docs/` and the changelog describe the behavior that exists. Update them in the same task as the code. `scripts/check_docs.py` checks links, settings, commands and section parity of the Russian twins. Every paragraph and list item is one line (markdownlint `MD013` is off).

## Working economy

- Read narrowly: `rg -n`, `sed -n 'a,bp'`, `wc -l`. Open a whole file only to rewrite most of it.
- Do mechanical changes with a throwaway script outside the repository (for example in `/tmp`) and delete it afterwards. After a script that rewrites code, run `python -m compileall -q`.
- Cap command output (`-q`, `| tail -n 30`). Batch independent commands. Run targeted tests while editing and the full gates once at the end.
- Do not restate this file or narrate steps; report results.
