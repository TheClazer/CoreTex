"""Surgical Word OOXML parser.

Reads a .docx file (as bytes) and walks its OOXML tree, producing a typed
``IRDocument``. The parser is the only place in the system that reads Word
XML; downstream layers (renderer, handlers) consume only the IR.

Owner: P2. Reference: word_latex_bible.pdf §2 layer 2 and team distribution.
"""

from __future__ import annotations

import logging
import zipfile
from io import BytesIO
from typing import List, Optional

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from lxml import etree

from app.converter.ir_schema import (
    CitationNode,
    EquationNode,
    FootnoteNode,
    HeadingNode,
    HyperlinkNode,
    ImageNode,
    IRDocument,
    IRNode,
    ListItemNode,
    ListNode,
    PageBreakNode,
    ParagraphNode,
    RunNode,
    TableCellNode,
    TableNode,
    TableRowNode,
    TextAlign,
)

logger = logging.getLogger(__name__)

# Namespace map used for raw lxml queries.
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALIGN_MAP = {
    "left": TextAlign.LEFT,
    "start": TextAlign.LEFT,
    "center": TextAlign.CENTER,
    "centre": TextAlign.CENTER,
    "right": TextAlign.RIGHT,
    "end": TextAlign.RIGHT,
    "both": TextAlign.JUSTIFY,
    "justify": TextAlign.JUSTIFY,
}


def _alignment_from_jc(jc_elem) -> TextAlign:
    if jc_elem is None:
        return TextAlign.LEFT
    val = jc_elem.get(qn("w:val")) or ""
    return _ALIGN_MAP.get(val.lower(), TextAlign.LEFT)


def _paragraph_alignment(p: Paragraph) -> TextAlign:
    pPr = p._p.find(qn("w:pPr"))
    if pPr is None:
        return TextAlign.LEFT
    return _alignment_from_jc(pPr.find(qn("w:jc")))


def _heading_level(p: Paragraph) -> Optional[int]:
    """Return 1..4 if ``p`` is a Heading 1..4, else None."""
    style = (p.style.name or "").strip() if p.style else ""
    if not style.lower().startswith("heading"):
        # Word also marks titles with 'Title' style; treat as H1.
        if style.lower() == "title":
            return 1
        return None
    # 'Heading 1' -> 1
    parts = style.split()
    try:
        lvl = int(parts[-1])
    except (ValueError, IndexError):
        return None
    return max(1, min(lvl, 4))


def _is_code_font(run) -> bool:
    """Detect a monospace/code run by inspecting its rFonts."""
    rPr = run._element.find(qn("w:rPr"))
    if rPr is None:
        return False
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        return False
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        font = rFonts.get(qn(attr)) or ""
        if any(token in font.lower() for token in ("courier", "consolas", "mono", "menlo")):
            return True
    return False


def _run_text(run) -> str:
    """Collect text from a w:r element including tabs and line breaks."""
    out: list[str] = []
    for child in run._element.iter():
        tag = etree.QName(child).localname
        if tag == "t":
            out.append(child.text or "")
        elif tag == "tab":
            out.append("\t")
        elif tag == "br":
            out.append("\n")
    return "".join(out)


def _build_runs(paragraph: Paragraph) -> List[RunNode]:
    runs: List[RunNode] = []
    for r in paragraph.runs:
        text = _run_text(r)
        if not text:
            continue
        runs.append(
            RunNode(
                text=text,
                bold=bool(r.bold),
                italic=bool(r.italic),
                underline=bool(r.underline),
                code=_is_code_font(r),
            )
        )
    return runs


def _has_page_break(paragraph: Paragraph) -> bool:
    return paragraph._p.find(f".//{qn('w:br')}[@{qn('w:type')}='page']") is not None


# ---------------------------------------------------------------------------
# List detection
# ---------------------------------------------------------------------------

def _list_info(paragraph: Paragraph) -> Optional[tuple[int, int]]:
    """Return (numId, ilvl) if paragraph is a list item, else None.

    Primary signal is the OOXML ``w:numPr`` element. Fallback signal is the
    paragraph style name (``List Number``, ``List Bullet``, ``List Bullet 2``
    etc.) — needed for documents whose styles point at numbering definitions
    that python-docx doesn't auto-create until rendered.
    """
    pPr = paragraph._p.find(qn("w:pPr"))
    if pPr is not None:
        numPr = pPr.find(qn("w:numPr"))
        if numPr is not None:
            numId_el = numPr.find(qn("w:numId"))
            ilvl_el = numPr.find(qn("w:ilvl"))
            if numId_el is not None:
                num_id = int(numId_el.get(qn("w:val"), "0"))
                ilvl = int(ilvl_el.get(qn("w:val"), "0")) if ilvl_el is not None else 0
                return num_id, ilvl

    # Style-name fallback. Map common style names to a synthetic numId.
    style = (paragraph.style.name or "") if paragraph.style else ""
    sl = style.lower()
    if not (sl.startswith("list number") or sl.startswith("list bullet") or sl == "list paragraph"):
        return None
    # Synthetic numId: 1000 for ordered, 2000 for unordered. ilvl from trailing digit.
    base = 1000 if "number" in sl else 2000
    tail = sl.replace("list number", "").replace("list bullet", "").strip()
    try:
        ilvl = int(tail) - 1 if tail else 0
    except ValueError:
        ilvl = 0
    return base, max(0, ilvl)


def _is_ordered_list(doc: DocxDocument, num_id: int) -> bool:
    """Inspect numbering.xml to determine whether the list is ordered."""
    # Synthetic IDs from style-name fallback.
    if num_id == 1000:
        return True
    if num_id == 2000:
        return False
    numbering = getattr(doc.part, "numbering_part", None)
    if numbering is None:
        return False
    root = numbering.element
    num = root.find(f"{qn('w:num')}[@{qn('w:numId')}='{num_id}']")
    if num is None:
        return False
    abs_ref = num.find(qn("w:abstractNumId"))
    if abs_ref is None:
        return False
    abs_id = abs_ref.get(qn("w:val"))
    abs_def = root.find(f"{qn('w:abstractNum')}[@{qn('w:abstractNumId')}='{abs_id}']")
    if abs_def is None:
        return False
    lvl = abs_def.find(f"{qn('w:lvl')}[@{qn('w:ilvl')}='0']")
    if lvl is None:
        return False
    numFmt = lvl.find(qn("w:numFmt"))
    if numFmt is None:
        return False
    fmt = (numFmt.get(qn("w:val")) or "").lower()
    return fmt not in ("bullet", "none")


def _flush_list(buffer: list[tuple[int, ListItemNode]], doc, num_id: int) -> ListNode:
    """Turn a flat (ilvl, item) buffer into a nested ListNode tree."""
    # Build nested tree using a stack.
    roots: List[ListItemNode] = []
    stack: List[tuple[int, ListItemNode]] = []
    for ilvl, item in buffer:
        item.level = ilvl
        while stack and stack[-1][0] >= ilvl:
            stack.pop()
        if not stack:
            roots.append(item)
        else:
            stack[-1][1].sub_items.append(item)
        stack.append((ilvl, item))
    return ListNode(ordered=_is_ordered_list(doc, num_id), items=roots)


# ---------------------------------------------------------------------------
# Hyperlink, equation, citation detection
# ---------------------------------------------------------------------------

def _extract_hyperlinks(paragraph: Paragraph, doc: DocxDocument) -> List[HyperlinkNode]:
    out: List[HyperlinkNode] = []
    for hlink in paragraph._p.findall(qn("w:hyperlink")):
        rid = hlink.get(qn("r:id"))
        url = ""
        if rid is not None:
            try:
                url = paragraph.part.rels[rid].target_ref or ""
            except KeyError:
                url = ""
        runs: List[RunNode] = []
        for r_elem in hlink.findall(qn("w:r")):
            text_parts: list[str] = []
            for t in r_elem.findall(qn("w:t")):
                text_parts.append(t.text or "")
            text = "".join(text_parts)
            if text:
                runs.append(RunNode(text=text))
        if url and runs:
            out.append(HyperlinkNode(url=url, runs=runs))
    return out


def _extract_equations(paragraph: Paragraph) -> List[EquationNode]:
    """Find OMML oMath / oMathPara elements inside a paragraph."""
    out: List[EquationNode] = []
    # Display equations (oMathPara) — block-level
    for math_para in paragraph._p.findall(qn("m:oMathPara")):
        xml = etree.tostring(math_para, encoding="unicode")
        out.append(EquationNode(omml_xml=xml, display=True))
    # Inline equations — exclude those nested inside oMathPara already captured.
    for math in paragraph._p.findall(qn("m:oMath")):
        if math.getparent().tag == qn("m:oMathPara"):
            continue
        xml = etree.tostring(math, encoding="unicode")
        out.append(EquationNode(omml_xml=xml, display=False))
    return out


def _extract_citations(paragraph: Paragraph) -> List[CitationNode]:
    """Pull Word citation fields out of a paragraph.

    Word emits citations as a sequence of w:r elements at the paragraph level:

        <w:r><w:fldChar w:fldCharType="begin"/></w:r>
        <w:r><w:instrText> CITATION ... </w:instrText></w:r>
        <w:r><w:fldChar w:fldCharType="separate"/></w:r>
        <w:r><w:t>[1]</w:t></w:r>           ← display text lives here
        <w:r><w:fldChar w:fldCharType="end"/></w:r>

    We find each w:instrText containing CITATION, walk *up to its parent
    w:r*, then iterate forward over paragraph-level siblings (other w:r
    elements) until we hit the matching fldChar end, collecting w:t text
    after a fldChar separate marker.
    """
    out: List[CitationNode] = []
    for instr in paragraph._p.findall(f".//{qn('w:instrText')}"):
        if not instr.text or "CITATION" not in instr.text.upper():
            continue

        # The w:instrText is inside a w:r; walk forward across paragraph siblings.
        run_elem = instr.getparent()
        if run_elem is None:
            continue
        sibling = run_elem.getnext()
        display = ""
        seen_separator = False
        while sibling is not None:
            tag = etree.QName(sibling).localname
            if tag == "r":
                fld = sibling.find(qn("w:fldChar"))
                if fld is not None:
                    fc_type = fld.get(qn("w:fldCharType"))
                    if fc_type == "separate":
                        seen_separator = True
                    elif fc_type == "end":
                        break
                elif seen_separator:
                    for t in sibling.findall(qn("w:t")):
                        if t.text:
                            display += t.text
            sibling = sibling.getnext()

        raw = etree.tostring(instr, encoding="unicode")
        out.append(CitationNode(display_text=display or "?", raw_xml=raw, source_id=None))
    return out


# ---------------------------------------------------------------------------
# Footnotes
# ---------------------------------------------------------------------------

def _load_footnotes(doc: DocxDocument) -> dict[str, List[RunNode]]:
    """Parse word/footnotes.xml and return {id: runs}."""
    out: dict[str, List[RunNode]] = {}
    part = getattr(doc.part, "footnotes_part", None) or getattr(
        doc.part.package, "footnotes_part", None
    )
    if part is None:
        # python-docx doesn't expose footnotes natively; reach through package.
        for rel in doc.part.rels.values():
            if rel.reltype.endswith("/footnotes"):
                part = rel.target_part
                break
    if part is None:
        return out
    root = etree.fromstring(part.blob) if hasattr(part, "blob") else part.element
    for fn in root.findall(qn("w:footnote")):
        fn_id = fn.get(qn("w:id"))
        if fn_id in (None, "-1", "0"):
            continue
        runs: List[RunNode] = []
        for t in fn.findall(f".//{qn('w:t')}"):
            if t.text:
                runs.append(RunNode(text=t.text))
        out[fn_id] = runs
    return out


def _extract_footnote_refs(paragraph: Paragraph, footnotes: dict) -> List[FootnoteNode]:
    out: List[FootnoteNode] = []
    for ref in paragraph._p.findall(f".//{qn('w:footnoteReference')}"):
        fn_id = ref.get(qn("w:id"))
        runs = footnotes.get(fn_id, [])
        if runs:
            out.append(FootnoteNode(runs=runs))
    return out


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def _extract_images(paragraph: Paragraph, docx_zip: zipfile.ZipFile, counter: list[int]) -> List[ImageNode]:
    out: List[ImageNode] = []
    blips = paragraph._p.findall(f".//{qn('a:blip')}")
    for blip in blips:
        rid = blip.get(qn("r:embed"))
        if not rid:
            continue
        try:
            rel = paragraph.part.rels[rid]
        except KeyError:
            continue
        target = rel.target_ref
        # Compose the zip path: rel target is relative to word/
        zip_path = target if target.startswith("word/") else f"word/{target}"
        try:
            data = docx_zip.read(zip_path)
        except KeyError:
            continue
        counter[0] += 1
        ext = zip_path.rsplit(".", 1)[-1].lower()
        filename = f"figure_{counter[0]:03d}.{ext}"
        out.append(ImageNode(filename=filename, image_data=data))
    return out


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _parse_cell(cell: _Cell) -> TableCellNode:
    runs: List[RunNode] = []
    align = TextAlign.LEFT
    for p in cell.paragraphs:
        if align == TextAlign.LEFT:
            align = _paragraph_alignment(p)
        runs.extend(_build_runs(p))
    # Detect spans
    tcPr = cell._tc.find(qn("w:tcPr"))
    col_span = 1
    row_span = 1
    if tcPr is not None:
        gridSpan = tcPr.find(qn("w:gridSpan"))
        if gridSpan is not None:
            try:
                col_span = int(gridSpan.get(qn("w:val"), "1"))
            except ValueError:
                col_span = 1
        vMerge = tcPr.find(qn("w:vMerge"))
        if vMerge is not None and vMerge.get(qn("w:val")) == "restart":
            row_span = 2  # heuristic; refined below
    return TableCellNode(runs=runs, col_span=col_span, row_span=row_span, alignment=align)


def _parse_table(table: Table) -> TableNode:
    rows: List[TableRowNode] = []
    col_count = 0
    for idx, row in enumerate(table.rows):
        cells = [_parse_cell(c) for c in row.cells]
        col_count = max(col_count, sum(c.col_span for c in cells))
        # First row is treated as header unless the table only has one row.
        is_header = idx == 0 and len(table.rows) > 1
        rows.append(TableRowNode(cells=cells, is_header=is_header))
    # Aggregate column alignment from majority of cells in column 0..n
    col_alignments: List[TextAlign] = []
    for c_idx in range(col_count):
        votes: dict[TextAlign, int] = {}
        for row in rows:
            if c_idx < len(row.cells):
                a = row.cells[c_idx].alignment
                votes[a] = votes.get(a, 0) + 1
        if votes:
            col_alignments.append(max(votes.items(), key=lambda kv: kv[1])[0])
        else:
            col_alignments.append(TextAlign.LEFT)
    return TableNode(rows=rows, col_alignments=col_alignments)


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def parse_docx(docx_bytes: bytes) -> IRDocument:
    """Parse a .docx file's bytes into an IRDocument.

    Raises:
        ValueError: when the bytes are not a valid OOXML zip.
    """
    if not docx_bytes.startswith(b"PK\x03\x04"):
        raise ValueError("Not a valid .docx (missing PK zip magic bytes)")

    doc: DocxDocument = Document(BytesIO(docx_bytes))
    docx_zip = zipfile.ZipFile(BytesIO(docx_bytes))

    warnings: List[str] = []
    nodes: List[IRNode] = []
    title: Optional[str] = None
    footnotes = _load_footnotes(doc)
    img_counter = [0]

    # Buffer for collecting consecutive list-item paragraphs.
    list_buffer: list[tuple[int, ListItemNode]] = []
    list_num_id: Optional[int] = None

    def flush_list():
        nonlocal list_buffer, list_num_id
        if list_buffer and list_num_id is not None:
            nodes.append(_flush_list(list_buffer, doc, list_num_id))
        list_buffer = []
        list_num_id = None

    # Walk the body in document order so paragraphs and tables remain interleaved.
    body = doc.element.body
    for child in body.iterchildren():
        tag = etree.QName(child).localname

        if tag == "p":
            p = Paragraph(child, doc)
            info = _list_info(p)
            if info is not None:
                num_id, ilvl = info
                if list_num_id is None:
                    list_num_id = num_id
                elif num_id != list_num_id:
                    flush_list()
                    list_num_id = num_id
                runs = _build_runs(p)
                list_buffer.append((ilvl, ListItemNode(runs=runs, level=ilvl)))
                continue

            flush_list()

            # Page break-only paragraph
            if _has_page_break(p) and not p.text.strip():
                nodes.append(PageBreakNode())
                continue

            # Heading
            level = _heading_level(p)
            runs = _build_runs(p)
            if level is not None and runs:
                hn = HeadingNode(level=level, runs=runs)
                nodes.append(hn)
                if title is None and level == 1:
                    title = "".join(r.text for r in runs).strip()
                continue

            # Block-level extractions that REPLACE a paragraph
            equations = _extract_equations(p)
            images = _extract_images(p, docx_zip, img_counter)
            hyperlinks = _extract_hyperlinks(p, doc)
            citations = _extract_citations(p)
            footnote_refs = _extract_footnote_refs(p, footnotes)

            # If the paragraph contains a display equation by itself, prefer the
            # equation node.
            if equations and not runs and not images:
                nodes.extend(equations)
                continue

            # Image-only paragraph
            if images and not runs:
                nodes.extend(images)
                continue

            # Otherwise emit a paragraph; attach inline hyperlinks/citations as
            # follow-on nodes (renderer respects document order).
            if runs:
                nodes.append(ParagraphNode(runs=runs, alignment=_paragraph_alignment(p)))
            nodes.extend(hyperlinks)
            nodes.extend(citations)
            nodes.extend(equations)
            nodes.extend(footnote_refs)
            nodes.extend(images)

            if _has_page_break(p):
                nodes.append(PageBreakNode())

        elif tag == "tbl":
            flush_list()
            table = Table(child, doc)
            try:
                nodes.append(_parse_table(table))
            except Exception as e:  # pragma: no cover - defensive
                warnings.append(f"Failed to parse table: {e}")

        elif tag == "sectPr":
            continue

    flush_list()

    return IRDocument(title=title, nodes=nodes, warnings=warnings)
