"""LaTeX character escape layer.

Single source of truth for converting raw text strings into LaTeX-safe
strings. MUST run on every string emitted by the renderer (paragraphs,
table cells, captions, headings, footnotes, hyperlink display text).
A reserved character that slips through unescaped causes a pdflatex
compilation failure.

Reference: word_latex_bible.pdf section 3 + team distribution P3 notes.
"""

from __future__ import annotations

import re

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

# Unicode math glyphs that appear in academic Word docs but break pdflatex
# in text mode. Each maps to a LaTeX command wrapped in `$...$`; consecutive
# math characters are merged by `_collapse_math_runs` below so we don't emit
# pathological output like `$\mathbb{R}$$^b$`.
#
# Coverage: blackboard-bold capitals, set-theory operators, common Greek
# letters, comparison / arithmetic operators, super/subscript digits and
# letters, arrows, calculus, and infinity. Add more here when you need them
# — escape_latex automatically picks them up.
_UNICODE_MATH: dict[str, str] = {
    # Blackboard bold
    "ℝ": r"\mathbb{R}", "ℕ": r"\mathbb{N}", "ℤ": r"\mathbb{Z}",
    "ℚ": r"\mathbb{Q}", "ℂ": r"\mathbb{C}", "𝔽": r"\mathbb{F}",
    # Set theory
    "∈": r"\in", "∉": r"\notin", "∋": r"\ni",
    "⊂": r"\subset", "⊆": r"\subseteq", "⊃": r"\supset", "⊇": r"\supseteq",
    "∪": r"\cup", "∩": r"\cap", "∅": r"\emptyset", "∖": r"\setminus",
    # Logic
    "∧": r"\land", "∨": r"\lor", "¬": r"\neg",
    "∀": r"\forall", "∃": r"\exists", "∄": r"\nexists",
    # Comparison
    "≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "≈": r"\approx",
    "≡": r"\equiv", "≅": r"\cong", "≜": r"\triangleq",
    # Arithmetic
    "×": r"\times", "÷": r"\div", "±": r"\pm", "∓": r"\mp",
    "−": "-", "‐": "-", "‑": "-",  # unicode minus / hyphens → math minus
    "⁄": "/",  # fraction slash
    "·": r"\cdot",  # NOTE: also in _UNICODE as \textperiodcentered;
                    # math mapping wins for academic context
    "⋅": r"\cdot",
    # Calculus / analysis
    "∞": r"\infty", "∂": r"\partial", "∇": r"\nabla",
    "∑": r"\sum", "∏": r"\prod", "∫": r"\int", "∬": r"\iint", "∭": r"\iiint",
    "√": r"\sqrt{}",
    # Arrows
    "→": r"\to", "←": r"\leftarrow", "↔": r"\leftrightarrow",
    "⇒": r"\Rightarrow", "⇐": r"\Leftarrow", "⇔": r"\Leftrightarrow",
    "↦": r"\mapsto",
    # Greek lowercase
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\epsilon", "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta",
    "ι": r"\iota", "κ": r"\kappa", "λ": r"\lambda", "μ": r"\mu",
    "ν": r"\nu", "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho",
    "σ": r"\sigma", "τ": r"\tau", "υ": r"\upsilon", "φ": r"\phi",
    "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
    # Greek uppercase
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda",
    "Ξ": r"\Xi", "Π": r"\Pi", "Σ": r"\Sigma", "Φ": r"\Phi",
    "Ψ": r"\Psi", "Ω": r"\Omega",
    # Superscripts
    "⁰": "^0", "¹": "^1", "²": "^2", "³": "^3", "⁴": "^4",
    "⁵": "^5", "⁶": "^6", "⁷": "^7", "⁸": "^8", "⁹": "^9",
    "⁺": "^+", "⁻": "^-", "⁼": "^=", "⁽": "^(", "⁾": "^)",
    "ⁿ": "^n", "ⁱ": "^i", "ᵃ": "^a", "ᵇ": "^b", "ᶜ": "^c",
    "ᵈ": "^d", "ᵉ": "^e", "ᶠ": "^f", "ᵍ": "^g", "ʰ": "^h",
    "ʲ": "^j", "ᵏ": "^k", "ˡ": "^l", "ᵐ": "^m", "ᵒ": "^o",
    "ᵖ": "^p", "ʳ": "^r", "ˢ": "^s", "ᵗ": "^t", "ᵘ": "^u",
    "ᵛ": "^v", "ʷ": "^w", "ˣ": "^x", "ʸ": "^y", "ᶻ": "^z",
    # Subscripts
    "₀": "_0", "₁": "_1", "₂": "_2", "₃": "_3", "₄": "_4",
    "₅": "_5", "₆": "_6", "₇": "_7", "₈": "_8", "₉": "_9",
    "₊": "_+", "₋": "_-", "₌": "_=",
    "ₐ": "_a", "ₑ": "_e", "ᵢ": "_i", "ⱼ": "_j", "ₖ": "_k",
    "ₗ": "_l", "ₘ": "_m", "ₙ": "_n", "ₒ": "_o", "ₚ": "_p",
    "ᵣ": "_r", "ₛ": "_s", "ₜ": "_t", "ᵤ": "_u", "ᵥ": "_v",
    "ₓ": "_x",
    # Misc
    "ℓ": r"\ell", "ℏ": r"\hbar", "ℵ": r"\aleph",
    "‖": r"\|", "⟨": r"\langle", "⟩": r"\rangle",  # norms and inner products
    "°": r"^\circ",  # NOTE: also in _UNICODE as \textdegree;
                     # math mapping wins for academic context (e.g. "45°")
}


# Combining diacritics that LaTeX renders via math-mode accent commands.
# `X̃` is the codepoint sequence U+0058 U+0303 (base + combining tilde) and
# must become `\tilde{X}` (in math mode) before pdflatex sees it. We do this
# in a regex pre-pass so the result then flows through the normal math
# escape machinery and merges cleanly with adjacent math glyphs.
_COMBINING_ACCENT = {
    "̀": "grave",   # X̀
    "́": "acute",   # X́
    "̂": "hat",     # X̂
    "̃": "tilde",   # X̃
    "̄": "bar",     # X̄
    "̆": "breve",   # X̆
    "̇": "dot",     # Ẋ
    "̈": "ddot",    # Ẍ (diaeresis as double-dot)
    "̊": "mathring",  # X̊
    "̌": "check",   # X̌
    "⃗": "vec",     # X⃗
    "⃑": "overrightarrow",  # X⃑
}

# Use a broad Unicode-letter class so combining marks attach correctly to
# Greek (α, β…), Cyrillic, accented Latin, etc. — not just A-Za-z0-9.
# `\w` won't do — that omits Greek script in some builds. We use the explicit
# letter category via the `\p{L}` analogue: match "any character that is not
# a combining mark itself, then one or more combining marks".
_COMBINING_PATTERN = "|".join(re.escape(c) for c in _COMBINING_ACCENT)
_COMBINING_RE = re.compile(
    r"([^\s\\{}$_^])((?:" + _COMBINING_PATTERN + r")+)"
)


def _apply_combining_accents(text: str) -> str:
    """Wrap base+combining sequences in math accent commands.

    Handles:
    - Greek + accent: α̃ → $\\tilde{\\alpha}$  (via secondary pass below)
    - Multiple marks: X̃̂ → $\\hat{\\tilde{X}}$ (nesting in order of appearance)
    - Latin + accent: X̃ → $\\tilde{X}$
    """
    def sub(m: re.Match[str]) -> str:
        base = m.group(1)
        marks = m.group(2)
        # If the base is itself a Unicode math glyph (e.g. Greek α), expand
        # it inline so the subsequent _UNICODE_MATH pass doesn't double-wrap.
        if base in _UNICODE_MATH:
            inner: str = _UNICODE_MATH[base]
        else:
            inner = base
        # Nest accents in source order: first mark becomes innermost wrapper.
        for mark in marks:
            cmd = _COMBINING_ACCENT.get(mark)
            if cmd is None:
                continue
            inner = f"\\{cmd}{{{inner}}}"
        return f"{_MATH_OPEN}{inner}{_MATH_CLOSE}"

    return _COMBINING_RE.sub(sub, text)


def has_math_glyphs(text: str) -> bool:
    """Does the text contain any character that needs amssymb/math mode?"""
    if any(ch in _UNICODE_MATH for ch in text):
        return True
    return _COMBINING_RE.search(text) is not None


# Sentinel wrapping each math glyph before substitution so we can later
# collapse adjacent ones into a single $...$ region.
_MATH_OPEN = "\x00MO\x00"
_MATH_CLOSE = "\x00MC\x00"
_MATH_RUN_RE = re.compile(re.escape(_MATH_CLOSE) + re.escape(_MATH_OPEN))

# Inside a math region, collapse `^a^b^c` → `^{abc}` (and same for `_`).
# Without this, pdflatex raises "Double superscript" on adjacent super/sub
# Unicode glyphs like `ᵇˣⁿˣᵈ`.
_SUPERSCRIPT_RE = re.compile(r"(?:\^([A-Za-z0-9+\-=()])){2,}")
_SUBSCRIPT_RE = re.compile(r"(?:_([A-Za-z0-9+\-=()])){2,}")


def _collapse_scripts(match: re.Match[str], prefix: str) -> str:
    chars = re.findall(r"[\^_]([A-Za-z0-9+\-=()])", match.group(0))
    return f"{prefix}{{{''.join(chars)}}}"


def escape_latex(text: str) -> str:
    """Escape arbitrary text into a LaTeX-safe string.

    Three passes:
    1. Backslash → sentinel, then escape remaining reserved chars.
    2. Apply typography Unicode (em-dash, curly quotes, etc.).
    3. Apply math-glyph Unicode wrapped in sentinels, then merge adjacent
       math runs into a single ``$…$`` region.

    The merge step turns `ℝᵇˣⁿˣᵈ` into a clean `$\\mathbb{R}^b^x^n^x^d$`
    instead of `$\\mathbb{R}$$^b$$^x$$^n$$^x$$^d$`.
    """
    if not text:
        return ""

    # Phase 1 — reserved characters
    text = text.replace("\\", _BACKSLASH_PLACEHOLDER)
    for src, repl in _RESERVED[1:]:  # skip the backslash rule (handled above)
        text = text.replace(src, repl)

    # Phase 2a — combining accents (X̃ → $\tilde{X}$). Must run before the
    # single-glyph math substitutions so the base letter survives intact.
    text = _apply_combining_accents(text)

    # Phase 2b — math glyphs (before typography so e.g. `·` math mapping
    # takes precedence over `\textperiodcentered`)
    for src, repl in _UNICODE_MATH.items():
        text = text.replace(src, f"{_MATH_OPEN}{repl}{_MATH_CLOSE}")

    # Phase 3 — typography Unicode
    for src, repl in _UNICODE:
        text = text.replace(src, repl)

    # Phase 4 — collapse adjacent math runs, then group consecutive
    # super/subscripts so pdflatex doesn't choke on "double superscript",
    # then swap sentinels for $.
    text = _MATH_RUN_RE.sub("", text)
    text = _SUPERSCRIPT_RE.sub(lambda m: _collapse_scripts(m, "^"), text)
    text = _SUBSCRIPT_RE.sub(lambda m: _collapse_scripts(m, "_"), text)
    text = text.replace(_MATH_OPEN, "$").replace(_MATH_CLOSE, "$")

    # Phase 5 — restore backslash placeholder
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
