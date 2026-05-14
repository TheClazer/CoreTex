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


def column_spec(table: TableNode) -> str:
    """Return the ``{lcr}``-style column specification for a tabular env."""
    if not table.col_alignments:
        # Fall back to inferring from the widest row.
        widths = [sum(c.col_span for c in row.cells) for row in table.rows] or [1]
        return "l" * max(widths)
    return "".join(_ALIGN_LETTER[a] for a in table.col_alignments)


def total_columns(table: TableNode) -> int:
    if table.col_alignments:
        return len(table.col_alignments)
    if not table.rows:
        return 0
    return max(sum(c.col_span for c in row.cells) for row in table.rows)
