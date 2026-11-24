# Copyright (c) 2026 Nikolai Zelensky
"""Tests for Russian document checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.docs_checks.russian import check_russian_documents, check_section_parity

if TYPE_CHECKING:
    from pathlib import Path


def test_accepts_russian_sections_in_the_english_order(tmp_path: Path) -> None:
    (tmp_path / "guide.md").write_text("## 1. Setup\n## 2. Usage\n", encoding="utf-8")
    (tmp_path / "guide.ru.md").write_text(
        "## 1. Установка\n## 2. Работа\n", encoding="utf-8"
    )
    expected_empty: list[str] = []

    errors = check_section_parity(tmp_path)

    assert errors == expected_empty, "matching numbered sections must pass"


def test_reports_russian_sections_in_another_order(tmp_path: Path) -> None:
    (tmp_path / "guide.md").write_text("## 1. Setup\n## 2. Usage\n", encoding="utf-8")
    (tmp_path / "guide.ru.md").write_text(
        "## 2. Работа\n## 1. Установка\n", encoding="utf-8"
    )
    expected = ["guide.ru.md: H2 section order differs from guide.md"]

    errors = check_section_parity(tmp_path)

    assert errors == expected, "a different section order must be reported"


def test_reports_a_different_section_count(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("## Alpha\n## Beta\n", encoding="utf-8")
    (tmp_path / "notes.ru.md").write_text("## Альфа\n", encoding="utf-8")
    expected = ["notes.ru.md: H2 section count differs from notes.md (1 != 2)"]

    errors = check_section_parity(tmp_path)

    assert errors == expected, "a different section count must be reported"


def test_reports_a_russian_document_without_an_english_twin(tmp_path: Path) -> None:
    (tmp_path / "orphan.ru.md").write_text("## Сирота\n", encoding="utf-8")
    expected = ["orphan.ru.md: missing English twin"]

    errors = check_section_parity(tmp_path)

    assert errors == expected, "a Russian document needs an English twin"


def test_accepts_a_russian_document_with_cyrillic(tmp_path: Path) -> None:
    (tmp_path / "faq.ru.md").write_text("# FAQ: вопросы\n", encoding="utf-8")
    expected_empty: list[str] = []

    errors = check_russian_documents(tmp_path)

    assert errors == expected_empty, "a document with Cyrillic must pass"


def test_reports_a_russian_document_without_cyrillic(tmp_path: Path) -> None:
    (tmp_path / "faq.ru.md").write_text("# FAQ: questions\n", encoding="utf-8")
    expected = ["faq.ru.md: no Cyrillic characters"]

    errors = check_russian_documents(tmp_path)

    assert errors == expected, "a Russian document without Cyrillic must be reported"
