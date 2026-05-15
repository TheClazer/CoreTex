"""Table column-alignment + LaTeX column spec helpers.

The parser fills ``TableNode.col_alignments`` from the Word XML ``<w:jc>``
element. This handler converts that into the ``l``/``c``/``r`` column
specification string consumed by the ``tabular`` environment.

Owner: P4.
"""

from __future__ import annotations

from app.converter.ir_schema import TableNode, TextAlign

_ALIGN_LETTER = {
    TextAlign.LEFT: "l",
    TextAlign.CENTER: "c",
    TextAlign.RIGHT: "r",
    TextAlign.JUSTIFY: "l",
}

# If any cell in a column has more than this many characters of text content,
# we switch that column to a wrapping ``p{width}`` block. Plain ``l``/``c``/
# ``r`` columns don't wrap, so a paragraph in a cell would run off the page.
_WRAP_THRESHOLD = 40


def _column_needs_wrap(table: TableNode, col_idx: int) -> bool:
    for row in table.rows:
        if col_idx >= len(row.cells):
            continue
        cell = row.cells[col_idx]
        chars = sum(len(r.text) for r in cell.runs)
        if chars > _WRAP_THRESHOLD:
            return True
    return False


def column_spec(table: TableNode) -> str:
    """Return the column specification for a tabular env.

    Each column is one of:
    - ``l`` / ``c`` / ``r`` — fixed alignment, no wrap (short cells)
    - ``p{0.25\\linewidth}`` — wrapping block (long cells)

    We pick wrap mode per column based on the maximum cell text length so
    long-text columns don't push the table off the page.
    """
    n = len(table.col_alignments) if table.col_alignments else 0
    if n == 0:
        widths = [sum(c.col_span for c in row.cells) for row in table.rows] or [1]
        n = max(widths)
        alignments: list[TextAlign] = [TextAlign.LEFT] * n
    else:
        alignments = list(table.col_alignments)

    # Pre-compute which columns need a wrap block.
    wrap_cols = {i for i in range(n) if _column_needs_wrap(table, i)}
    if not wrap_cols:
        return "".join(_ALIGN_LETTER[a] for a in alignments)

    # Distribute width across wrapping columns. Reserve a tiny slice for
    # the non-wrapping columns; the rest is split evenly.
    fixed = n - len(wrap_cols)
    wrap_width = max(0.15, (1.0 - 0.08 * fixed) / max(1, len(wrap_cols)))
    parts: list[str] = []
    for i, a in enumerate(alignments):
        if i in wrap_cols:
            parts.append(f"p{{{wrap_width:.2f}\\linewidth}}")
        else:
            parts.append(_ALIGN_LETTER[a])
    return "".join(parts)


def total_columns(table: TableNode) -> int:
    if table.col_alignments:
        return len(table.col_alignments)
    if not table.rows:
        return 0
    return max(sum(c.col_span for c in row.cells) for row in table.rows)
