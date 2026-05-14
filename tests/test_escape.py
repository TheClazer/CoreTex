"""Unit tests for the LaTeX character escape layer.

Covers every one of the 10 reserved characters individually and in
combination, plus Unicode edge cases called out in the bible.
"""

from __future__ import annotations

import pytest

from app.converter.escape import escape_latex, escape_url


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("100%", r"100\%"),
        ("A & B", r"A \& B"),
        ("$5", r"\$5"),
        ("#hash", r"\#hash"),
        ("snake_case", r"snake\_case"),
        ("x^2", r"x\^{}2"),
        ("{key}", r"\{key\}"),
        ("~user", r"\textasciitilde{}user"),
        ("a\\b", r"a\textbackslash{}b"),
    ],
)
def test_each_reserved_character(raw, expected):
    assert escape_latex(raw) == expected


def test_backslash_escaped_first():
    """Backslash must not be re-escaped by subsequent rules."""
    # Input contains both backslash and underscore.
    assert escape_latex("a\\_b") == r"a\textbackslash{}\_b"


def test_multiple_reserved_in_same_string():
    raw = "50% & $#_^"
    out = escape_latex(raw)
    assert out == r"50\% \& \$\#\_\^{}"


def test_unicode_em_dash_and_quotes():
    assert escape_latex("a — b") == "a --- b"
    assert escape_latex("“hi”") == "``hi''"
    assert escape_latex("‘x’") == "`x'"
    assert escape_latex("en–dash") == "en--dash"


def test_unicode_ellipsis():
    assert escape_latex("end…") == r"end\ldots{}"


def test_non_breaking_space():
    assert escape_latex("a b") == "a~b"


def test_empty_string():
    assert escape_latex("") == ""


def test_url_escape_keeps_slashes_and_colon():
    assert escape_url("https://example.com/a_b") == "https://example.com/a_b"


def test_url_escape_percent_and_hash():
    assert escape_url("https://x.com/a%20b#frag") == r"https://x.com/a\%20b\#frag"


# ── Unicode math glyph tests ───────────────────────────────────────────

def test_blackboard_R_becomes_math_mode():
    # Spaces between glyphs keep the math regions separate. Adjacent
    # glyphs merge (see test_adjacent_math_glyphs_are_merged).
    assert escape_latex("X ∈ ℝ") == r"X $\in$ $\mathbb{R}$"


def test_adjacent_math_glyphs_are_merged():
    """ℝᵇˣⁿˣᵈ should collapse to one math region with grouped superscripts."""
    out = escape_latex("ℝᵇˣⁿˣᵈ")
    # exactly one opening $ and one closing $
    assert out.count("$") == 2
    assert r"\mathbb{R}" in out
    # super/subscript chars are grouped into a single ^{...} so pdflatex
    # doesn't raise "double superscript".
    assert "^{bxnxd}" in out


def test_consecutive_subscripts_grouped():
    out = escape_latex("x₁₂₃")
    assert "_{123}" in out
    assert "^" not in out


def test_greek_letters_render_as_math():
    out = escape_latex("α + β = γ")
    assert r"\alpha" in out
    assert r"\beta" in out
    assert r"\gamma" in out
    # the + sign is just text, so it sits between math regions
    assert "$" in out


def test_set_operators():
    out = escape_latex("A ⊆ B ∪ C")
    assert r"\subseteq" in out
    assert r"\cup" in out


def test_comparison_operators():
    assert "≤" not in escape_latex("a ≤ b")
    assert r"\leq" in escape_latex("a ≤ b")
    assert r"\neq" in escape_latex("x ≠ y")
    assert r"\approx" in escape_latex("π ≈ 3.14")


def test_subscripts_and_superscripts():
    out = escape_latex("x₁² + x₂² = r²")
    assert "_1" in out and "^2" in out and "_2" in out


def test_infinity_and_calculus():
    out = escape_latex("∫₀^∞ f(x) dx")
    assert r"\int" in out
    assert r"\infty" in out


def test_has_math_glyphs():
    from app.converter.escape import has_math_glyphs

    assert has_math_glyphs("X ∈ ℝ")
    assert has_math_glyphs("α")
    assert not has_math_glyphs("plain ASCII text")
    assert not has_math_glyphs("—curly quotes “like these”")
