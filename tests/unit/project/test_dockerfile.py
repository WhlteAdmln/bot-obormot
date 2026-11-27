# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the base image reference of the Dockerfile."""

import re
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]


@pytest.fixture(name="dockerfile_lines")
def dockerfile_lines_fixture() -> list[str]:
    """Read the lines of the Dockerfile."""
    return (ROOT_DIR / "Dockerfile").read_text("utf-8").splitlines()


def test_pins_the_base_image_by_digest(dockerfile_lines: list[str]) -> None:
    pinned_pattern = re.compile(r"ARG PYTHON_IMAGE=\S+:\S+@sha256:[0-9a-f]{64}")
    pinned_lines = [line for line in dockerfile_lines if pinned_pattern.fullmatch(line)]
    expected_count = 1
    assert len(pinned_lines) == expected_count, "the base image carries no digest"


def test_builds_every_stage_from_the_pinned_base(dockerfile_lines: list[str]) -> None:
    from_lines = [line for line in dockerfile_lines if line.startswith("FROM ")]
    pinned_prefix = "FROM ${PYTHON_IMAGE} "
    unpinned = [line for line in from_lines if not line.startswith(pinned_prefix)]
    expected_empty: list[str] = []
    assert unpinned == expected_empty, "a stage bypasses the pinned base image"
