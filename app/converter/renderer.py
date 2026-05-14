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


def _render_list_items(items: List[ListItemNode], ordered: bool) -> str:
    env = "enumerate" if ordered else "itemize"
    out: list[str] = []
    for item in items:
        out.append(f"  \\item {_render_runs(item.runs)}")
        if item.sub_items:
            # Nested lists inherit the parent's ordering, per the bible.
            out.append(f"  \\begin{{{env}}}")
            out.append(_render_list_items(item.sub_items, ordered))
            out.append(f"  \\end{{{env}}}")
    return "\n".join(out)


def _render_list(node: ListNode) -> str:
    env = "enumerate" if node.ordered else "itemize"
    return f"\\begin{{{env}}}\n{_render_list_items(node.items, node.ordered)}\n\\end{{{env}}}"


def _render_table(node: TableNode) -> str:
    spec = column_spec(node)
    cols = total_columns(node) or 1
    lines: list[str] = [
        "\\begin{table}[!htbp]",
        "\\centering",
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
    if node.caption:
        lines.append(f"\\caption{{{escape_latex(node.caption)}}}")
    lines.append("\\end{table}")
    return "\n".join(lines)


def _render_image(node: ImageNode) -> str:
    # [!htbp] is more permissive than [h]: try Here, then Top of page, then
    # Bottom, then Page of floats. The `!` overrides LaTeX's internal
    # placement-failure thresholds. Eliminates the "float specifier changed"
    # warnings that pdflatex emits when [h] alone can't fit.
    width = "0.8\\linewidth"
    parts = [
        "\\begin{figure}[!htbp]",
        "\\centering",
        f"\\includegraphics[width={width}]{{figures/{node.filename}}}",
    ]
    if node.caption:
        parts.append(f"\\caption{{{escape_latex(node.caption)}}}")
    parts.append("\\end{figure}")
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
    display = escape_latex(node.display_text)
    warnings.append(f"[CITATION] '{node.display_text}' kept as plain text — manual BibTeX needed.")
    return f"{display} % [CITATION -- manual BibTeX needed]"


def _render_page_break() -> str:
    return "\\newpage"


# ---------------------------------------------------------------------------
# Preamble injection
# ---------------------------------------------------------------------------

def _required_packages(doc: IRDocument) -> List[str]:
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

    pkgs: List[str] = ["\\usepackage[utf8]{inputenc}", "\\usepackage[margin=1in]{geometry}"]
    if has_eq or has_math_unicode:
        pkgs.append("\\usepackage{amsmath}")
        pkgs.append("\\usepackage{amssymb}")
    if has_link:
        pkgs.append("\\usepackage{hyperref}")
    if has_img:
        pkgs.append("\\usepackage{graphicx}")
    if has_table:
        pkgs.append("\\usepackage{booktabs}")
    if has_list:
        pkgs.append("\\usepackage{enumitem}")
    # footnote pkg is part of base LaTeX; we don't need an explicit usepackage.
    return pkgs


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def render(doc: IRDocument, template: str = "article", metadata: dict | None = None) -> tuple[str, List[str]]:
    """Render an IRDocument to a complete .tex source string.

    Returns ``(latex_source, warnings)``. Warnings accumulated here are
    appended to whatever the parser already collected by the caller.
    """
    template = template.lower()
    if template not in _TEMPLATE_FILES:
        raise ValueError(f"Unknown template: {template!r}")

    warnings: List[str] = []
    body_parts: list[str] = []

    for node in doc.nodes:
        if isinstance(node, HeadingNode):
            body_parts.append(_render_heading(node))
        elif isinstance(node, ParagraphNode):
            body_parts.append(_render_paragraph(node))
        elif isinstance(node, ListNode):
            body_parts.append(_render_list(node))
        elif isinstance(node, TableNode):
            body_parts.append(_render_table(node))
        elif isinstance(node, ImageNode):
            body_parts.append(_render_image(node))
        elif isinstance(node, EquationNode):
            body_parts.append(_render_equation(node))
        elif isinstance(node, FootnoteNode):
            body_parts.append(_render_footnote(node))
        elif isinstance(node, HyperlinkNode):
            body_parts.append(_render_hyperlink(node))
        elif isinstance(node, CitationNode):
            body_parts.append(_render_citation(node, warnings))
        elif isinstance(node, PageBreakNode):
            body_parts.append(_render_page_break())
        else:  # pragma: no cover - defensive
            warnings.append(f"Unsupported IR node type: {type(node).__name__}")

    body = "\n\n".join(body_parts)
    packages = _required_packages(doc)

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
