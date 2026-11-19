# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Creation of the protected ``.env`` file from the packaged template."""

import os
import tempfile
from importlib.resources import files
from pathlib import Path

from bot_obormot.config.token import is_valid_bot_token

TOKEN_PLACEHOLDER = "BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN"  # noqa: S105
SUPERVISOR_PLACEHOLDER = "SUPERVISOR_ID=REPLACE_WITH_NUMERIC_TELEGRAM_ID"


def load_env_template() -> str:
    """Read the ``.env`` template shipped inside the package."""
    template = files("bot_obormot").joinpath("templates", "env.example")
    return template.read_text(encoding="utf-8")


def render_env_content(*, token: str | None, supervisor: int | None) -> str:
    """Fill the template placeholders that were provided."""
    content = load_env_template()
    if token is not None:
        if not is_valid_bot_token(token):
            message = "The Telegram token has an invalid format."
            raise ValueError(message)
        content = content.replace(TOKEN_PLACEHOLDER, f"BOT_TOKEN={token}", 1)
    if supervisor is not None:
        if supervisor <= 0:
            message = "The supervisor ID must be a positive integer."
            raise ValueError(message)
        content = content.replace(
            SUPERVISOR_PLACEHOLDER, f"SUPERVISOR_ID={supervisor}", 1
        )
    return content


def write_initial_env(
    home: Path,
    *,
    token: str | None = None,
    supervisor: int | None = None,
    force: bool = False,
) -> Path:
    """Create ``<home>/.env`` with mode 600; never overwrite without ``force``."""
    content = render_env_content(token=token, supervisor=supervisor)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    env_path = home / ".env"

    descriptor, temporary_name = tempfile.mkstemp(prefix=".env.", dir=home)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        temporary_path.chmod(0o600)
        if force:
            temporary_path.replace(env_path)
        else:
            os.link(temporary_path, env_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return env_path
