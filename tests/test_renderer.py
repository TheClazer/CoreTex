"""Renderer unit + regression tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.converter.ir_schema import (
    CitationNode,
    HeadingNode,
    HyperlinkNode,
    ImageNode,
    IRDocument,
    ListItemNode,
    ListNode,
    ParagraphNode,
    RunNode,
    TableCellNode,
    TableNode,
    TableRowNode,
    TextAlign,
)
from app.converter.parser import parse_docx
from app.converter.renderer import render
from tests.golden.generate import generate_all

GOLDEN_DIR = Path(__file__).parent / "golden"


@pytest.fixture(scope="session", autouse=True)
def _ensure_golden():
    if not list(GOLDEN_DIR.glob("*.docx")):
        generate_all()


def _doc(*nodes) -> IRDocument:
    return IRDocument(nodes=list(nodes))


def test_heading_emits_section():
    out, _ = render(_doc(HeadingNode(level=1, runs=[RunNode(text="Intro")])))
    assert "\\section{Intro}" in out


def test_subsubsection_paragraph():
    out, _ = render(_doc(HeadingNode(level=4, runs=[RunNode(text="X")])))
    assert "\\paragraph{X}" in out


def test_bold_italic_underline_code_runs():
    p = ParagraphNode(runs=[
        RunNode(text="b", bold=True),
        RunNode(text="i", italic=True),
        RunNode(text="u", underline=True),
        RunNode(text="c", code=True),
    ])
    out, _ = render(_doc(p))
    assert "\\textbf{b}" in out
    assert "\\textit{i}" in out
    assert "\\underline{u}" in out
    assert "\\texttt{c}" in out


def test_unordered_list_with_nesting():
    inner = ListItemNode(runs=[RunNode(text="sub")])
    top = ListItemNode(runs=[RunNode(text="top")], sub_items=[inner])
    out, _ = render(_doc(ListNode(ordered=False, items=[top])))
    assert "\\begin{itemize}" in out
    assert "\\item top" in out
    assert "\\item sub" in out


def test_ordered_list_enumerates():
    item = ListItemNode(runs=[RunNode(text="one")])
    out, _ = render(_doc(ListNode(ordered=True, items=[item])))
    assert "\\begin{enumerate}" in out


def test_table_renders_tabular_with_booktabs():
    cell = TableCellNode(runs=[RunNode(text="x")])
    row = TableRowNode(cells=[cell, cell, cell], is_header=True)
    table = TableNode(
        rows=[row, TableRowNode(cells=[cell, cell, cell])],
        col_alignments=[TextAlign.LEFT, TextAlign.CENTER, TextAlign.RIGHT],
    )
    out, _ = render(_doc(table))
    assert "\\begin{tabular}{lcr}" in out
    assert "\\toprule" in out
    assert "\\midrule" in out
    assert "\\bottomrule" in out


def test_hyperlink_escapes_url_correctly():
    h = HyperlinkNode(url="https://x.com/a#b", runs=[RunNode(text="link")])
    out, _ = render(_doc(h))
    assert "\\href{https://x.com/a\\#b}{link}" in out


def test_citation_appends_warning():
    c = CitationNode(display_text="[1]", raw_xml="<x/>")
    out, warns = render(_doc(c))
    assert "[CITATION" in out
    assert any("[CITATION]" in w for w in warns)


def test_smart_preamble_inclusion():
    # Doc without images/links/equations should not pull in those packages.
    out, _ = render(_doc(ParagraphNode(runs=[RunNode(text="hi")])))
    assert "graphicx" not in out
    assert "hyperref" not in out
    assert "amsmath" not in out

    # Doc with an image should pull in graphicx.
    img = ImageNode(filename="figure_001.png", image_data=b"\x89PNG")
    out2, _ = render(_doc(img))
    assert "graphicx" in out2


def test_escape_layer_applied_to_paragraph_text():
    p = ParagraphNode(runs=[RunNode(text="50% & $#_")])
    out, _ = render(_doc(p))
    assert "50\\% \\& \\$\\#\\_" in out


def test_unknown_template_raises():
    with pytest.raises(ValueError):
        render(_doc(), template="beamer")


@pytest.mark.parametrize("template", ["article", "ieee", "acm", "springer"])
def test_all_templates_wrap_document(template):
    p = ParagraphNode(runs=[RunNode(text="hello")])
    out, _ = render(_doc(p), template=template)
    assert "\\documentclass" in out
    assert "\\begin{document}" in out
    assert "\\end{document}" in out
    assert "hello" in out


def test_all_golden_docs_render_to_latex():
    docs = sorted(p for p in GOLDEN_DIR.glob("*.docx") if not p.name.startswith("~$"))
    assert docs
    for path in docs:
        ir = parse_docx(path.read_bytes())
        out, _ = render(ir, template="article")
        assert "\\documentclass" in out
        assert "\\end{document}" in out
