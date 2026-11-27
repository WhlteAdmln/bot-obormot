# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""A fake ``mv`` that breaks the switch of a staged virtual environment."""

import shlex
import shutil
from pathlib import Path
from typing import Literal

STUB_TEMPLATE = """#!/bin/sh
case "$1" in
*/.venv.new) ;;
*) exec {real_mv} "$@" ;;
esac
{action}
"""

ACTIONS = {
    "move": "exit 1",
    "relocate": (
        '{real_mv} "$@" || exit\n'
        'rm "$2/bin/python"\n'
        "printf '#!/bin/sh\\nexit 1\\n' >\"$2/bin/python\"\n"
        'chmod 755 "$2/bin/python"'
    ),
}


def create_mv_stub(directory: Path, failure: Literal["move", "relocate"]) -> Path:
    """Write an ``mv`` that fails on the staged environment and return its folder.

    ``move`` fails the move of ``.venv.new``; ``relocate`` moves it and replaces
    the moved interpreter with one that exits with an error, so the path update
    fails. Every other move runs the real ``mv``.
    """
    real_mv = shutil.which("mv")
    if real_mv is None:
        message = "The mv command is required."
        raise RuntimeError(message)
    quoted = shlex.quote(real_mv)
    directory.mkdir(parents=True, exist_ok=True)
    stub = directory / "mv"
    stub.write_text(
        STUB_TEMPLATE.format(
            real_mv=quoted, action=ACTIONS[failure].format(real_mv=quoted)
        ),
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return directory
