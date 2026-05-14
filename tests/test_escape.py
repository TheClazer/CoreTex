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
