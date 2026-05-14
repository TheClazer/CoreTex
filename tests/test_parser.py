"""Parser unit + regression tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.converter.ir_schema import (
    HeadingNode,
    IRDocument,
    ListNode,
    PageBreakNode,
    ParagraphNode,
    RunNode,
    TableNode,
)
from app.converter.parser import parse_docx
from tests.golden.generate import generate_all

GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.fixture(scope="session", autouse=True)
def _ensure_golden_files():
    """Generate synthetic golden docs once per test session."""
    if not list(GOLDEN_DIR.glob("*.docx")):
        generate_all()


def _read(name: str) -> bytes:
    path = GOLDEN_DIR / name
    if not path.exists():
        generate_all()
    return path.read_bytes()


def test_parser_rejects_non_docx():
    with pytest.raises(ValueError):
        parse_docx(b"not a real docx")


def test_plain_text_parses_to_paragraphs():
    doc = parse_docx(_read("01_plain_text.docx"))
    assert isinstance(doc, IRDocument)
    paragraphs = [n for n in doc.nodes if isinstance(n, ParagraphNode)]
    assert len(paragraphs) >= 2
    assert all(isinstance(r, RunNode) for p in paragraphs for r in p.runs)


def test_headings_levels_1_to_4_captured():
    doc = parse_docx(_read("02_all_headings.docx"))
    headings = [n for n in doc.nodes if isinstance(n, HeadingNode)]
    assert {h.level for h in headings} == {1, 2, 3, 4}


def test_bold_italic_underline_flags():
    doc = parse_docx(_read("03_bold_italic.docx"))
    runs = [r for n in doc.nodes if isinstance(n, ParagraphNode) for r in n.runs]
    assert any(r.bold for r in runs)
    assert any(r.italic for r in runs)
    assert any(r.underline for r in runs)


def test_lists_detected_with_correct_ordering():
    doc = parse_docx(_read("04_lists.docx"))
    lists = [n for n in doc.nodes if isinstance(n, ListNode)]
    assert len(lists) >= 2
    assert any(lst.ordered for lst in lists)
    assert any(not lst.ordered for lst in lists)


def test_table_structure():
    doc = parse_docx(_read("05_table.docx"))
    tables = [n for n in doc.nodes if isinstance(n, TableNode)]
    assert tables, "expected at least one table"
    t = tables[0]
    assert len(t.rows) == 3
    assert all(len(r.cells) >= 3 for r in t.rows)


def test_page_break_detected():
    doc = parse_docx(_read("12_page_breaks.docx"))
    assert any(isinstance(n, PageBreakNode) for n in doc.nodes)


def test_unicode_paragraph_survives():
    doc = parse_docx(_read("14_unicode.docx"))
    text = "".join(r.text for n in doc.nodes if isinstance(n, ParagraphNode) for r in n.runs)
    assert "—" in text or "–" in text or "“" in text


def test_all_golden_docs_parse_cleanly():
    """Every .docx in tests/golden/ must parse without exceptions."""
    docs = sorted(p for p in GOLDEN_DIR.glob("*.docx") if not p.name.startswith("~$"))
    assert docs, "no golden docs available"
    for path in docs:
        result = parse_docx(path.read_bytes())
        assert isinstance(result, IRDocument), f"{path.name} produced non-IR"
        # Body must not be empty.
        assert result.nodes, f"{path.name} produced zero nodes"
