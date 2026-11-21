# Contributing

1. Clone the repository and enter the `bot-obormot` directory.
2. Use Python 3.11 or newer, GNU Make, and FFmpeg. ShellCheck is installed with development dependencies.
3. Create a focused branch for your change.
4. Create a virtual environment with `make venv` (Python 3.13 by default; override `PYTHON_VERSION` for another supported version).
5. Install development dependencies with `make install-dev`.
6. Keep changes focused and preserve existing application behavior unless the task requires otherwise.
7. Add or update tests for changed behavior. Tests must not require network access, a GPU, or real secrets.
8. Run `make fix` to apply Ruff fixes and formatting.
9. Run `make check` before opening a pull request.
10. LLM agents must also follow the rules in [AGENTS.md](AGENTS.md).
11. Open a pull request describing the change and the checks you ran. Do not include secrets, local environments, or generated build artifacts.

## Useful commands

| Command | What it does |
| --- | --- |
| `make check` | Lint, types, dependency, dead-code and import gates, tests, documentation checks. |
| `make integration` | Integration tests (tests marked `integration`). |
| `make installer` | Real-shell installer tests. |
| `make docs-check` | Links, settings, commands and README section parity. |
| `make docker` | Validate `compose.yaml` and build the image. |

Shared files: `.editorconfig`, `.pre-commit-config.yaml`, `.github/renovate.json5`,
`scripts/check_lock.py`, `scripts/check_vendored.py`, `scripts/build_release.sh`, `.markdownlint-cli2.yaml`, `AGENTS.md`, the `ruff` and `mypy` tables of
`pyproject.toml`, `bot_obormot/log_filters.py` and `bot_obormot/env_readers.py` are copies
of the audiodoc files. audiodoc is the source of truth: change it there first, copy the
file here, then run `python scripts/check_vendored.py --other ../audiodoc`.

## Dependency updates

Renovate is the only tool that updates dependencies, opens pull requests and merges them; its configuration is `.github/renovate.json5`. Minor and patch updates are merged automatically after every check passes, except for the parsers and network libraries listed in the configuration, which are merged automatically only for patches. Major updates and `0.x` releases wait for a human. A release must be 14 days old before it is proposed; security fixes are not delayed.

Dependabot alerts and the dependency graph stay enabled as a second source of vulnerability reports, and Renovate reads the alerts. Dependabot security updates and version updates are disabled so that only one tool opens pull requests.
