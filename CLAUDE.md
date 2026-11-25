# CLAUDE.md

@AGENTS.md

This file is shared byte for byte by the sibling repositories listed in `scripts/check_vendored.py`. It holds the development standards and says where the work comes from. It names no project: project facts live in `README.md`, `CONTRIBUTING.md` and `pyproject.toml`, and the planned work lives in the GitHub issues of each repository.

## Language

Answer in the language of the user's messages. Code, comments, documentation, `CHANGELOG.md` and GitHub issues are in English; a document with a `.ru.md` twin is updated in both languages.

## Session start

1. List the open issues with `gh issue list --state open`. The open GitHub issues of the repository are the only source of truth for planned work. Do not rely on memory or on earlier conversations.
2. Run `git status` and `git log --oneline -5` (read-only). If the working tree has uncommitted changes, tell the user and ask whether they belong to the previous issue before touching anything.
3. Show the open issues to the user (number, label, title) and ask whether they pick one or leave the choice to the agent. If the user's first message names an issue or asks for something else, follow that instead.
4. When the choice is left to the agent, take the label with the highest priority that has open issues, in the order `bug`, `refactor`, `enhancement`, `documentation`, read those issues and pick the one that is easiest to finish. Propose it in two or three lines (number, title, what will change) and wait for the user to confirm.

One issue is one session. Do not start a second issue in the same session unless the user asks for it.

## Working on an issue

- An issue has a title prefix (`[Bug]:`, `[Feature]:`, `[Refactor]:` or `[Docs]:`) and exactly one label: `bug`, `refactor`, `enhancement` or `documentation`. Do what the issue describes (for a bug: the expected behavior; otherwise: the proposed solution) and nothing else (rule 12 of `AGENTS.md`). One issue gets one pull request in its repository.
- A related finding does not go into the diff. Draft a new issue for it in the same form (title prefix, one label, the sections of the matching template in `.github/ISSUE_TEMPLATE/`), show the draft to the user and create it with `gh issue create` only after the user approves it.
- An issue never refers to the sibling repository: no links to its issues or pull requests and no instructions to work there. A change to a shared file (see the shared-files section of `CONTRIBUTING.md`) has its own issue in each repository. It is done from the source-of-truth repository named in `CONTRIBUTING.md`: edit both working trees in one session, then run `scripts/check_vendored.py --other <path>` in both; each repository gets its own pull request that closes its own issue. If the sibling is not reachable, tell the user to restart Claude Code with `--add-dir <path>`.
- Behavior does not change unless the issue says so. If a fix would change behavior or a public API, stop and ask one short question, and continue with the rest meanwhile.
- If the issue turns out to be larger than one session, finish a clean part, draft new issues for the remainder as described above and say so.

## Completing an issue

1. Run `make check` (or `make -k check` to see every failure) and `scripts/check_vendored.py --other <path>` in every repository you changed. Every gate must be green. Say which gate could not run on this machine and why; never claim a gate passed without running it. After the final `make check`, run `make clean` in every repository where it ran, so no build, coverage or cache artifacts stay in the working tree.
2. Add entries under `[Unreleased]` in `CHANGELOG.md`, in the section order Added, Changed, Deprecated, Fixed, Removed, Security (`scripts/check_changelog.py` enforces it). Each entry is one short sentence that starts with a link to the issue (`[#<number>](<issue URL>)`); the details stay in the issue. A change to the agent instructions alone (`CLAUDE.md`, `AGENTS.md`) gets no entry, since it does not change the project.
3. Tell the user in plain words that the issue is finished: `#<number> done`, in the user's language, followed by a short summary: what changed, test count and coverage before and after, gates run, assumptions, anything not verified, and which suppressions the issue touched.
4. Ask the user to choose the delivery mode: manual or automatic. Manual: stop here; the user asks for each git step. Automatic: run the steps of "Git and CI" without further requests: create the branch, commit and push; show the pull request text and create the pull request after the user approves it; watch the checks with `gh pr checks --watch`; when every check passed and `gh pr view` shows the pull request mergeable, merge it, switch to `main` and pull. If a check fails or the pull request cannot be merged, stop and report what blocks it.
5. Suggest the next issue by the rule of the session start (number and title) and say that it needs a new session. Do not start it.

The issue is closed by its pull request: the pull request text contains `Closes #<number>`, so GitHub closes the issue when the pull request is merged. Do not close an issue by hand.

## Git and CI

Git and CI belong to the user. Without a request in the current session, do not run any command that writes to the repository or to a remote. Choosing the automatic mode in "Completing an issue" is such a request for the branch, commit, push, pull request and merge of that issue. Creating an issue follows the approval rule in "Working on an issue"; do not edit, label or close an issue the user did not ask about. When the user asks in the session, create a branch from the current state, `git add`, `git commit`, `git push -u origin <branch>` and open a pull request with `gh pr create`; show the pull request text to the user and wait for approval before creating it. When the user asks in the session to merge a pull request, first check with `gh pr checks` and `gh pr view` that every check passed and the pull request is mergeable without conflicts; otherwise report what blocks it and do not merge. Merge with `gh pr merge <number> --merge`, then run `git switch main` and `git pull --ff-only`. Never force-push, rebase, reset, tag, delete a branch, push to `main`, merge without a request in the session or change a pull request the user did not ask about. Read-only commands (`git status`, `diff`, `log`, `show`) are fine. The user watches CI and merges in the web interface unless they choose the automatic mode or ask the agent to merge. Do not rename files, CI workflows or CI jobs without the user's consent; an issue that asks for it counts as consent. Commit, issue and pull request text is English; the pull request text follows `.github/pull_request_template.md`, including the `Closes #<number>` line, and carries no generated-by attribution line: never add `🤖 Generated with [Claude Code](https://claude.com/claude-code)` or a similar line. Commit, issue and pull request text does not describe the local environment: no local or sibling paths (for example `--other ../<repo>`), user names, machine names or operating system details. Branch names, commit messages and pull request titles and text follow the style of the repository history: read the recent commits (`git log`) and merged pull requests (`gh pr list --state merged`) before writing, and do not add what that history does not use, such as issue numbers in titles.

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
- Coverage never drops and `fail_under` is never lowered. A gate that was green does not turn red. The test count does not fall, except for tests of functionality that the issue deletes; list them.
- Replace `Any` only where a precise type is obvious.

### Tests

New and changed tests follow these rules even where older tests do not yet; open issues track the gap.

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

`README.md`, `CONTRIBUTING.md`, `docs/` and the changelog describe the behavior that exists. Update them in the same issue as the code. `scripts/check_docs.py` checks links, settings, commands and section parity of the Russian twins. Every paragraph and list item is one line (markdownlint `MD013` is off).

## Working economy

- Read narrowly: `rg -n`, `sed -n 'a,bp'`, `wc -l`. Open a whole file only to rewrite most of it.
- Do mechanical changes with a throwaway script outside the repository (for example in `/tmp`) and delete it afterwards. After a script that rewrites code, run `python -m compileall -q`.
- Cap command output (`-q`, `| tail -n 30`). Batch independent commands. Run targeted tests while editing and the full gates once at the end.
- Do not restate this file or narrate steps; report results.
