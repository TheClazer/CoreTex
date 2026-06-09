"""Adjacent-run merger (v2 roadmap: run-merger optimisation).

Word frequently splits visually-identical text into many runs — per-word
formatting, spell-check boundaries, rsid revision tracking — which made the
rendered LaTeX needlessly verbose (``\textbf{H}\textbf{ello}``) and bloated
resume-style documents. This pass collapses every maximal sequence of
adjacent runs that share the same formatting flags into a single run.

Pure function over IR runs; the parser applies it at every place runs are
built (paragraphs, headings, list items, table cells, footnotes).
"""

from __future__ import annotations

from typing import List

from app.converter.ir_schema import RunNode


def _same_format(a: RunNode, b: RunNode) -> bool:
    return (
        a.bold == b.bold
        and a.italic == b.italic
        and a.underline == b.underline
        and a.code == b.code
    )


def merge_runs(runs: List[RunNode]) -> List[RunNode]:
    """Collapse adjacent runs with identical formatting into one run.

    Returns a new list; input nodes are not mutated. Empty-text runs are
    dropped (they render to nothing but defeat adjacency).
    """
    merged: List[RunNode] = []
    for run in runs:
        if run.text == "":
            continue
        if merged and _same_format(merged[-1], run):
            prev = merged[-1]
            merged[-1] = RunNode(
                text=prev.text + run.text,
                bold=prev.bold,
                italic=prev.italic,
                underline=prev.underline,
                code=prev.code,
            )
        else:
            merged.append(run)
    return merged
