"""v2 roadmap feature tests: run merger, BibTeX extraction, citation keys."""

from __future__ import annotations

import zipfile
from io import BytesIO

from app.converter.bibliography import extract_bibliography
from app.converter.ir_schema import CitationNode, IRDocument, ParagraphNode, RunNode
from app.converter.renderer import render
from app.converter.run_merger import merge_runs


# ---------------------------------------------------------------------------
# Run merger
# ---------------------------------------------------------------------------

def test_merge_collapses_same_format_runs():
    runs = [
        RunNode(text="Hel", bold=True),
        RunNode(text="lo", bold=True),
        RunNode(text=" world", bold=False),
    ]
    merged = merge_runs(runs)
    assert len(merged) == 2
    assert merged[0].text == "Hello" and merged[0].bold is True
    assert merged[1].text == " world" and merged[1].bold is False


def test_merge_drops_empty_runs_and_preserves_distinct_formats():
    runs = [
        RunNode(text="a", italic=True),
        RunNode(text="", italic=True),
        RunNode(text="b", italic=False),
        RunNode(text="c", italic=False),
    ]
    merged = merge_runs(merge_runs(runs))
    assert [r.text for r in merged] == ["a", "bc"]


def test_merge_reduces_rendered_wrapper_count():
    # Three bold fragments must render as ONE \textbf, not three.
    p = ParagraphNode(runs=merge_runs([
        RunNode(text="A", bold=True),
        RunNode(text="B", bold=True),
        RunNode(text="C", bold=True),
    ]))
    out, _ = render(IRDocument(nodes=[p]))
    assert out.count("\\textbf{") == 1
    assert "\\textbf{ABC}" in out


# ---------------------------------------------------------------------------
# BibTeX extraction
# ---------------------------------------------------------------------------

_SOURCES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<b:Sources xmlns:b="http://schemas.openxmlformats.org/officeDocument/2006/bibliography">
  <b:Source>
    <b:Tag>Smith2020</b:Tag>
    <b:SourceType>JournalArticle</b:SourceType>
    <b:Title>On Widgets</b:Title>
    <b:JournalName>Journal of Widgets</b:JournalName>
    <b:Year>2020</b:Year>
    <b:Volume>12</b:Volume>
    <b:Pages>3-14</b:Pages>
    <b:Author><b:Author><b:NameList>
      <b:Person><b:Last>Smith</b:Last><b:First>Jane</b:First></b:Person>
    </b:NameList></b:Author></b:Author>
  </b:Source>
</b:Sources>
"""


def _docx_with_sources() -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/bibliography/sources.xml", _SOURCES_XML)
    return buf.getvalue()


def test_extract_bibliography_parses_source():
    bib = extract_bibliography(_docx_with_sources())
    assert not bib.is_empty
    assert bib.key_for_tag("Smith2020") == "Smith2020"
    bibtex = bib.to_bibtex()
    assert "@article{Smith2020," in bibtex
    assert "author = {Smith, Jane}" in bibtex
    assert "journal = {Journal of Widgets}" in bibtex
    assert "year = {2020}" in bibtex
    assert "pages = {3--14}" in bibtex  # en-dash normalised for BibTeX


_SOURCES_SPECIAL = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<b:Sources xmlns:b="http://schemas.openxmlformats.org/officeDocument/2006/bibliography">
  <b:Source>
    <b:Tag>AT&amp;T2021</b:Tag>
    <b:SourceType>Report</b:SourceType>
    <b:Title>Cost_Model &amp; 50% Margins #1</b:Title>
    <b:Publisher>AT&amp;T Labs</b:Publisher>
    <b:Year>2021</b:Year>
    <b:Author><b:Author><b:NameList>
      <b:Person><b:Last>O'Neil_Smith</b:Last><b:First>A&amp;B</b:First></b:Person>
    </b:NameList></b:Author></b:Author>
  </b:Source>
</b:Sources>
"""


def test_bibtex_escapes_latex_special_chars():
    import zipfile as _zip
    from io import BytesIO as _BIO

    buf = _BIO()
    with _zip.ZipFile(buf, "w") as zf:
        zf.writestr("word/bibliography/sources.xml", _SOURCES_SPECIAL)
    bib = extract_bibliography(buf.getvalue())
    out = bib.to_bibtex()
    # Specials must be escaped in title/publisher/author, not left raw.
    assert r"\&" in out and r"\%" in out and r"\#" in out and r"\_" in out
    # No bare unescaped & survives in a field value line.
    for line in out.splitlines():
        if "=" in line:
            # every & on a value line must be backslash-escaped
            assert "&" not in line.replace(r"\&", "")


def test_extract_bibliography_absent_is_empty():
    empty_docx = BytesIO()
    with zipfile.ZipFile(empty_docx, "w") as zf:
        zf.writestr("word/document.xml", "<w:document/>")
    bib = extract_bibliography(empty_docx.getvalue())
    assert bib.is_empty
    assert bib.to_bibtex() == ""


# ---------------------------------------------------------------------------
# Citation rendering: resolved key -> \cite, unresolved -> plain-text fallback
# ---------------------------------------------------------------------------

def test_resolved_citation_renders_cite_no_warning():
    c = CitationNode(display_text="[1]", raw_xml="<x/>", source_id="Smith2020")
    out, warns = render(IRDocument(nodes=[c]))
    assert "\\cite{Smith2020}" in out
    assert not any("[CITATION]" in w for w in warns)


def test_unresolved_citation_keeps_plaintext_fallback():
    c = CitationNode(display_text="[2]", raw_xml="<x/>")  # source_id None
    out, warns = render(IRDocument(nodes=[c]))
    assert "[CITATION" in out
    assert any("[CITATION]" in w for w in warns)


def test_document_with_bibtex_emits_bibliography():
    out, _ = render(
        IRDocument(nodes=[ParagraphNode(runs=[RunNode(text="x")])], bibtex="@book{a,}"),
        template="article",
    )
    assert "\\bibliography{references}" in out
    assert "\\bibliographystyle{plain}" in out
