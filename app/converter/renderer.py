"""IR → LaTeX renderer.

Pure-Python walker over an ``IRDocument`` that emits LaTeX source. Pandoc
is NEVER invoked here (see bible §6). Every text string passes through
``escape.escape_latex`` before emission. The rendered body is wrapped in
one of four Jinja2 document-class templates.

Owner: P3. Reference: bible §2 layer 5 + team distribution P3.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, List

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.converter.escape import escape_latex, escape_url, has_math_glyphs
from app.converter.handlers.table_handler import column_spec, total_columns
from app.converter.ir_schema import (
    CitationNode,
    EquationNode,
    FootnoteNode,
    HeadingNode,
    HyperlinkNode,
    ImageNode,
    IRDocument,
    ListItemNode,
    ListNode,
    PageBreakNode,
    ParagraphNode,
    RunNode,
    TableNode,
    TextAlign,
)

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(disabled_extensions=("j2", "tex.j2")),
    block_start_string="<%",
    block_end_string="%>",
    variable_start_string="<<",
    variable_end_string=">>",
    comment_start_string="<#",
    comment_end_string="#>",
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=StrictUndefined,
)

_HEADING_CMD = {1: "section", 2: "subsection", 3: "subsubsection", 4: "paragraph"}

_TEMPLATE_FILES = {
    "article": "article.tex.j2",
    "ieee": "ieee.tex.j2",
    "acm": "acm.tex.j2",
    "springer": "springer.tex.j2",
    "beamer": "beamer.tex.j2",
}


# ---------------------------------------------------------------------------
# Run + paragraph helpers
# ---------------------------------------------------------------------------

def _render_run(run: RunNode) -> str:
    out = escape_latex(run.text)
    # Layer formatting from inside out so wrappers nest cleanly.
    if run.code:
        out = f"\\texttt{{{out}}}"
    if run.underline:
        out = f"\\underline{{{out}}}"
    if run.italic:
        out = f"\\textit{{{out}}}"
    if run.bold:
        out = f"\\textbf{{{out}}}"
    return out


def _render_runs(runs: Iterable[RunNode]) -> str:
    return "".join(_render_run(r) for r in runs)


def _wrap_alignment(text: str, alignment: TextAlign) -> str:
    if alignment == TextAlign.CENTER:
        return f"\\begin{{center}}\n{text}\n\\end{{center}}"
    if alignment == TextAlign.RIGHT:
        return f"\\begin{{flushright}}\n{text}\n\\end{{flushright}}"
    if alignment == TextAlign.JUSTIFY:
        return text  # default
    return text


# ---------------------------------------------------------------------------
# Per-node renderers
# ---------------------------------------------------------------------------

def _render_heading(node: HeadingNode) -> str:
    cmd = _HEADING_CMD[node.level]
    return f"\\{cmd}{{{_render_runs(node.runs)}}}"


def _render_paragraph(node: ParagraphNode) -> str:
    text = _render_runs(node.runs)
    return _wrap_alignment(text, node.alignment)


# LaTeX's built-in enumerate nests at most 4 deep (itemize 6). Opening a 5th
# level aborts with "Too deeply nested." Word allows up to 9 list levels, so we
# cap the rendered nesting: items deeper than the limit are flattened into the
# deepest legal level instead of opening another environment.
_MAX_LIST_DEPTH = 4


def _render_list_items(items: List[ListItemNode], ordered: bool, depth: int = 1) -> str:
    env = "enumerate" if ordered else "itemize"
    out: list[str] = []
    for item in items:
        out.append(f"  \\item {_render_runs(item.runs)}")
        if item.sub_items:
            # Nested lists inherit the parent's ordering, per the bible.
            if depth < _MAX_LIST_DEPTH:
                out.append(f"  \\begin{{{env}}}")
                out.append(_render_list_items(item.sub_items, ordered, depth + 1))
                out.append(f"  \\end{{{env}}}")
            else:
                # Depth cap hit: keep sub-items at this level (compiles) rather
                # than opening an illegal 5th environment (hard error).
                out.append(_render_list_items(item.sub_items, ordered, depth))
    return "\n".join(out)


def _render_list(node: ListNode) -> str:
    env = "enumerate" if node.ordered else "itemize"
    return f"\\begin{{{env}}}\n{_render_list_items(node.items, node.ordered, 1)}\n\\end{{{env}}}"


def _render_table(node: TableNode, float_env: bool = True) -> str:
    spec = column_spec(node)
    cols = total_columns(node) or 1
    # Beamer frames cannot contain floats (the table/figure environments) —
    # with allowframebreaks LaTeX aborts with "Float(s) lost". In that mode we
    # emit a plain centered tabular instead (floats are meaningless on a slide).
    if float_env:
        lines: list[str] = [
            "\\begin{table}[!htbp]",
            "\\centering",
            f"\\begin{{tabular}}{{{spec}}}",
            "\\toprule",
        ]
    else:
        lines = [
            "\\begin{center}",
            f"\\begin{{tabular}}{{{spec}}}",
            "\\toprule",
        ]
    for r_idx, row in enumerate(node.rows):
        # Pad cells to total column count using col_span.
        rendered_cells: list[str] = []
        col_used = 0
        for cell in row.cells:
            content = _render_runs(cell.runs)
            if cell.col_span > 1:
                col_letter = {
                    TextAlign.CENTER: "c",
                    TextAlign.RIGHT: "r",
                    TextAlign.LEFT: "l",
                    TextAlign.JUSTIFY: "l",
                }.get(cell.alignment, "l")
                content = f"\\multicolumn{{{cell.col_span}}}{{{col_letter}}}{{{content}}}"
            rendered_cells.append(content)
            col_used += cell.col_span
        while col_used < cols:
            rendered_cells.append("")
            col_used += 1
        lines.append(" & ".join(rendered_cells) + " \\\\")
        if row.is_header:
            lines.append("\\midrule")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    if float_env:
        if node.caption:
            lines.append(f"\\caption{{{escape_latex(node.caption)}}}")
        lines.append("\\end{table}")
    else:
        # \caption is invalid outside a float; render it as plain centered text.
        if node.caption:
            lines.append(f"\\par\\smallskip{{\\small {escape_latex(node.caption)}}}")
        lines.append("\\end{center}")
    return "\n".join(lines)


def _render_image(node: ImageNode, float_env: bool = True) -> str:
    # [!htbp] is more permissive than [h]: try Here, then Top of page, then
    # Bottom, then Page of floats. The `!` overrides LaTeX's internal
    # placement-failure thresholds. Eliminates the "float specifier changed"
    # warnings that pdflatex emits when [h] alone can't fit.
    #
    # Beamer frames can't hold floats, so in that mode we emit a plain centered
    # \includegraphics (with the caption as text, since \caption needs a float).
    width = "0.8\\linewidth"
    include = f"\\includegraphics[width={width}]{{figures/{node.filename}}}"
    if float_env:
        parts = ["\\begin{figure}[!htbp]", "\\centering", include]
        if node.caption:
            parts.append(f"\\caption{{{escape_latex(node.caption)}}}")
        parts.append("\\end{figure}")
    else:
        parts = ["\\begin{center}", include]
        if node.caption:
            parts.append(f"\\par\\smallskip{{\\small {escape_latex(node.caption)}}}")
        parts.append("\\end{center}")
    return "\n".join(parts)


def _render_equation(node: EquationNode) -> str:
    body = node.latex_string or "?\\text{equation pending}"
    if node.display:
        return f"\\begin{{equation}}\n{body}\n\\end{{equation}}"
    return f"${body}$"


def _render_footnote(node: FootnoteNode) -> str:
    return f"\\footnote{{{_render_runs(node.runs)}}}"


def _render_hyperlink(node: HyperlinkNode) -> str:
    return f"\\href{{{escape_url(node.url)}}}{{{_render_runs(node.runs)}}}"


def _render_citation(node: CitationNode, warnings: List[str]) -> str:
    # v2: when the parser resolved this citation to a BibTeX key (source_id),
    # emit a real \cite — no warning, no manual work. Otherwise fall back to
    # the plain-text behaviour the v1 contract guarantees.
    if node.source_id:
        return f"\\cite{{{node.source_id}}}"
    display = escape_latex(node.display_text)
    warnings.append(f"[CITATION] '{node.display_text}' kept as plain text — manual BibTeX needed.")
    return f"{display} % [CITATION -- manual BibTeX needed]"


def _render_page_break() -> str:
    return "\\newpage"


# ---------------------------------------------------------------------------
# Preamble injection
# ---------------------------------------------------------------------------

def _required_packages(doc: IRDocument, is_beamer: bool = False) -> List[str]:
    has_eq = False
    has_link = False
    has_img = False
    has_table = False
    has_list = False
    has_footnote = False
    has_math_unicode = False

    def _runs_have_math(runs):
        return any(has_math_glyphs(r.text) for r in runs)

    def visit(node):
        nonlocal has_eq, has_link, has_img, has_table, has_list, has_footnote
        nonlocal has_math_unicode
        if isinstance(node, EquationNode):
            has_eq = True
        elif isinstance(node, HyperlinkNode):
            has_link = True
            if _runs_have_math(node.runs):
                has_math_unicode = True
        elif isinstance(node, ImageNode):
            has_img = True
        elif isinstance(node, TableNode):
            has_table = True
            for row in node.rows:
                for cell in row.cells:
                    if _runs_have_math(cell.runs):
                        has_math_unicode = True
        elif isinstance(node, ListNode):
            has_list = True

            def walk_items(items):
                nonlocal has_math_unicode
                for it in items:
                    if _runs_have_math(it.runs):
                        has_math_unicode = True
                    walk_items(it.sub_items)
            walk_items(node.items)
        elif isinstance(node, FootnoteNode):
            has_footnote = True
            if _runs_have_math(node.runs):
                has_math_unicode = True
        elif isinstance(node, (ParagraphNode, HeadingNode)):
            if _runs_have_math(node.runs):
                has_math_unicode = True

    for node in doc.nodes:
        visit(node)

    # Beamer manages its own page geometry; injecting `geometry` with margins
    # breaks slide layout, so we omit it. We DO keep inputenc so UTF-8 body
    # content is safe on older TeX (it is compatible with beamer).
    if is_beamer:
        pkgs: List[str] = ["\\usepackage[utf8]{inputenc}"]
    else:
        pkgs = ["\\usepackage[utf8]{inputenc}", "\\usepackage[margin=1in]{geometry}"]
    if has_eq or has_math_unicode:
        pkgs.append("\\usepackage{amsmath}")
        pkgs.append("\\usepackage{amssymb}")
    # Beamer already loads hyperref and graphicx internally, and enumitem
    # conflicts with beamer's own list handling — only add these for the
    # article-style templates.
    if has_link and not is_beamer:
        pkgs.append("\\usepackage{hyperref}")
    if has_img and not is_beamer:
        pkgs.append("\\usepackage{graphicx}")
    if has_table:
        pkgs.append("\\usepackage{booktabs}")
    if has_list and not is_beamer:
        pkgs.append("\\usepackage{enumitem}")
    # footnote pkg is part of base LaTeX; we don't need an explicit usepackage.
    return pkgs


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def _render_node(node, warnings: List[str], float_env: bool = True) -> str | None:
    """Render a single IR node to LaTeX, or None if unsupported.

    ``float_env`` is False for Beamer, where table/figure floats are illegal
    inside a frame and must be rendered as plain centered content.
    """
    if isinstance(node, HeadingNode):
        return _render_heading(node)
    if isinstance(node, ParagraphNode):
        return _render_paragraph(node)
    if isinstance(node, ListNode):
        return _render_list(node)
    if isinstance(node, TableNode):
        return _render_table(node, float_env=float_env)
    if isinstance(node, ImageNode):
        return _render_image(node, float_env=float_env)
    if isinstance(node, EquationNode):
        return _render_equation(node)
    if isinstance(node, FootnoteNode):
        return _render_footnote(node)
    if isinstance(node, HyperlinkNode):
        return _render_hyperlink(node)
    if isinstance(node, CitationNode):
        return _render_citation(node, warnings)
    if isinstance(node, PageBreakNode):
        return _render_page_break()
    warnings.append(f"Unsupported IR node type: {type(node).__name__}")  # pragma: no cover
    return None


def _render_flat_body(doc: IRDocument, warnings: List[str]) -> str:
    """Standard article-style body: nodes in order, blank-line separated."""
    parts = [r for node in doc.nodes if (r := _render_node(node, warnings)) is not None]
    if doc.bibtex:
        parts.append("\\bibliographystyle{plain}")
        parts.append("\\bibliography{references}")
    return "\n\n".join(parts)


def _is_pseudo_heading(node) -> bool:
    """A short, entirely-bold paragraph used as a de-facto heading.

    Many documents type their section titles as bold text instead of using
    Word heading styles. Without this, a whole report collapses into ONE
    Beamer frame (nothing to split on) and overflows off the slide. We treat a
    fully-bold, short, single-line paragraph as a slide boundary.
    """
    if not isinstance(node, ParagraphNode) or not node.runs:
        return False
    if not all(r.bold for r in node.runs):
        return False
    text = "".join(r.text for r in node.runs).strip()
    # Short, single-line, not a full sentence (headings rarely end in a period).
    return 0 < len(text) <= 70 and "\n" not in text and not text.endswith(".")


def _render_beamer_body(doc: IRDocument, warnings: List[str]) -> str:
    """Beamer body: split content into frames at heading boundaries.

    A new frame starts at each real H1/H2 heading OR each detected pseudo
    heading (short all-bold paragraph), so documents that type their titles as
    bold text still get sliced into slides instead of overflowing one frame.
    Deeper real headings become ``\\textbf`` lead-ins inside the current frame.

    Frame-break policy: a frame that contains a list uses plain ``[t]`` because
    ``[allowframebreaks]`` breaking *inside* an enumerate sends beamer's
    ``\\labelenumi`` into infinite recursion ("TeX capacity exceeded"). Frames
    without a list use ``[allowframebreaks]`` so long prose spills across
    continuation slides instead of being clipped.
    """
    frames: list[str] = []
    current_title: str | None = None
    current_parts: list[str] = []
    current_has_list = False
    real_heading_count = 0

    def flush():
        nonlocal current_has_list
        if not current_parts and current_title is None:
            return
        title_tex = current_title if current_title is not None else ""
        inner = "\n\n".join(current_parts).strip()
        opt = "t" if current_has_list else "allowframebreaks"
        frames.append(
            f"\\begin{{frame}}[{opt}]{{{title_tex}}}\n{inner}\n\\end{{frame}}"
        )

    for node in doc.nodes:
        if isinstance(node, PageBreakNode):
            continue  # page breaks are meaningless between slides
        if isinstance(node, HeadingNode) and node.level <= 2:
            flush()
            real_heading_count += 1
            current_title = _render_runs(node.runs)
            current_parts, current_has_list = [], False
            continue
        if _is_pseudo_heading(node):
            flush()
            # Title is inherently bold in beamer, so use the plain text.
            current_title = escape_latex("".join(r.text for r in node.runs).strip())
            current_parts, current_has_list = [], False
            continue
        if isinstance(node, HeadingNode):  # deeper heading → emphasised lead-in
            current_parts.append(f"\\textbf{{{_render_runs(node.runs)}}}\\par")
            continue
        if isinstance(node, ListNode):
            current_has_list = True
        # float_env=False: no table/figure floats inside a Beamer frame.
        rendered = _render_node(node, warnings, float_env=False)
        if rendered is not None:
            current_parts.append(rendered)
    flush()

    if real_heading_count == 0:
        warnings.append(
            "[BEAMER] This document has no Word heading styles, so slides were "
            "auto-detected from bold section titles. For a long report, the "
            "'article' or 'ieee' template usually reads better than slides."
        )

    if doc.bibtex:
        frames.append(
            "\\begin{frame}[allowframebreaks]{References}\n"
            "\\bibliographystyle{plain}\n\\bibliography{references}\n"
            "\\end{frame}"
        )
    return "\n\n".join(frames)


def render(doc: IRDocument, template: str = "article", metadata: dict | None = None) -> tuple[str, List[str]]:
    """Render an IRDocument to a complete .tex source string.

    Returns ``(latex_source, warnings)``. Warnings accumulated here are
    appended to whatever the parser already collected by the caller.
    """
    template = template.lower()
    if template not in _TEMPLATE_FILES:
        raise ValueError(f"Unknown template: {template!r}")

    is_beamer = template == "beamer"
    warnings: List[str] = []

    if is_beamer:
        body = _render_beamer_body(doc, warnings)
    else:
        body = _render_flat_body(doc, warnings)

    packages = _required_packages(doc, is_beamer=is_beamer)

    title = doc.title or (metadata or {}).get("title") or "Converted Document"
    author = (metadata or {}).get("author", "CoreTex Converter")

    tpl = _jinja_env.get_template(_TEMPLATE_FILES[template])
    rendered = tpl.render(
        body=body,
        packages="\n".join(packages),
        title=escape_latex(title),
        author=escape_latex(author),
        has_abstract=False,
    )
    return rendered, warnings
