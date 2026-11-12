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
