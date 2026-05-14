"""LaTeX character escape layer.

Single source of truth for converting raw text strings into LaTeX-safe
strings. MUST run on every string emitted by the renderer (paragraphs,
table cells, captions, headings, footnotes, hyperlink display text).
A reserved character that slips through unescaped causes a pdflatex
compilation failure.

Reference: word_latex_bible.pdf section 3 + team distribution P3 notes.
"""

from __future__ import annotations

# Order matters: backslash MUST be escaped first, otherwise subsequent
# escape replacements (which themselves introduce backslashes) will be
# double-escaped.
_RESERVED: tuple[tuple[str, str], ...] = (
    ("\\", r"\textbackslash{}"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("%", r"\%"),
    ("&", r"\&"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("^", r"\^{}"),
    ("~", r"\textasciitilde{}"),
)

# Typographic Unicode mappings to native LaTeX syntax.
_UNICODE: tuple[tuple[str, str], ...] = (
    ("—", "---"),
    ("–", "--"),
    ("…", r"\ldots{}"),
    ("“", "``"),
    ("”", "''"),
    ("‘", "`"),
    ("’", "'"),
    (" ", "~"),
    ("«", "<<"),
    ("»", ">>"),
    ("•", r"\textbullet{}"),
    ("·", r"\textperiodcentered{}"),
    ("©", r"\textcopyright{}"),
    ("®", r"\textregistered{}"),
    ("™", r"\texttrademark{}"),
    ("°", r"\textdegree{}"),
)


_BACKSLASH_PLACEHOLDER = "\x00BACKSLASH\x00"


def escape_latex(text: str) -> str:
    """Escape arbitrary text into a LaTeX-safe string.

    Backslash is shunted to a sentinel before the other reserved chars are
    escaped, then restored to ``\\textbackslash{}`` at the end. This keeps
    the ``{}`` introduced by the textbackslash macro from being re-escaped.
    """
    if not text:
        return ""
    text = text.replace("\\", _BACKSLASH_PLACEHOLDER)
    for src, repl in _RESERVED[1:]:  # skip the backslash rule
        text = text.replace(src, repl)
    for src, repl in _UNICODE:
        text = text.replace(src, repl)
    text = text.replace(_BACKSLASH_PLACEHOLDER, r"\textbackslash{}")
    return text


def escape_url(url: str) -> str:
    """Escape a URL for safe use as the first arg of \\href{URL}{...}."""
    if not url:
        return ""
    return (
        url.replace("\\", r"\textbackslash{}")
        .replace("%", r"\%")
        .replace("#", r"\#")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("^", r"\^{}")
        .replace("~", r"\~{}")
    )
