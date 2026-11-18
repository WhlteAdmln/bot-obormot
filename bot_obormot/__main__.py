# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Allow ``python -m bot_obormot`` to run the command-line interface."""

import sys

from bot_obormot.cli import main

if __name__ == "__main__":
    sys.exit(main())
