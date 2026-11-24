# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Typed environment readers that collect validation errors."""

from collections.abc import Mapping

from bot_obormot.env_readers import (
    get_bool,
    get_float,
    get_int,
    get_optional_int,
    parse_ids,
)


class EnvironmentReader:
    """Read typed values from one environment mapping and collect the errors."""

    def __init__(self, environ: Mapping[str, str]) -> None:
        """Copy the mapping and start with no errors."""
        self.environ = dict(environ)
        self.errors: list[str] = []

    def read_str(
        self,
        name: str,
        default: str,
        *,
        strip: bool = False,
        lower: bool = False,
    ) -> str:
        """Return a string value, optionally stripped and lowercased."""
        value = self.environ.get(name, default)
        if strip:
            value = value.strip()
        return value.lower() if lower else value

    def read_bool(self, name: str, *, default: bool) -> bool:
        """Return a boolean value or the default after recording an error."""
        try:
            return get_bool(
                name,
                default=default,
                environ=self.environ,
            )
        except ValueError as error:
            self.errors.append(str(error))
            return default

    def read_int(
        self,
        name: str,
        default: int,
        *,
        minimum: int = 1,
        required: bool = False,
    ) -> int:
        """Return an integer value or the default after recording an error."""
        raw_default = "" if required else str(default)
        try:
            return get_int(
                name,
                raw_default,
                minimum,
                environ=self.environ,
            )
        except ValueError as error:
            self.errors.append(str(error))
            return default

    def read_optional_int(self, name: str) -> int | None:
        """Return an optional integer or None after recording an error."""
        try:
            return get_optional_int(
                name,
                environ=self.environ,
            )
        except ValueError as error:
            self.errors.append(str(error))
            return None

    def read_float(
        self,
        name: str,
        default: float,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        """Return a float value or the default after recording an error."""
        try:
            return get_float(
                name,
                str(default),
                minimum=minimum,
                maximum=maximum,
                environ=self.environ,
            )
        except ValueError as error:
            self.errors.append(str(error))
            return default

    def read_ids(self, name: str) -> set[int]:
        """Return a set of Telegram IDs or an empty set after recording an error."""
        try:
            return parse_ids(name, environ=self.environ)
        except ValueError as error:
            self.errors.append(str(error))
            return set()
