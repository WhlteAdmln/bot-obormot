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
10. Open a pull request describing the change and the checks you ran. Do not include secrets, local environments, or generated build artifacts.

## Useful commands

| Command | What it does |
|---------|--------------|
| `make check` | Lint, types, dependency, dead-code and import gates, tests, documentation checks. |
| `make integration` | Integration tests (tests marked `integration`). |
| `make installer` | Real-shell installer tests; the legacy test needs `BOT_OBORMOT_LEGACY_SOURCE`. |
| `make docs-check` | Links, settings, commands and README section parity. |
| `make docker` | Validate `compose.yaml` and build the image. |

Shared files: `.editorconfig`, `.pre-commit-config.yaml`, `.github/dependabot.yml`,
`scripts/check_lock.py`, `scripts/check_vendored.py`, the `ruff` and `mypy` tables of
`pyproject.toml`, `bot_obormot/log_filters.py` and `bot_obormot/env_readers.py` are copies
of the audiodoc files. audiodoc is the source of truth: change it there first, copy the
file here, then run `python scripts/check_vendored.py --other ../audiodoc`.
