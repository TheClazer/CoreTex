"""Tests for the dependency-free direct OMML → LaTeX converter."""

from __future__ import annotations

from app.converter.handlers.omml_direct import omml_to_latex

_W = 'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"'


def _omath(inner: str) -> str:
    return f'<m:oMath {_W}>{inner}</m:oMath>'


def test_plain_run():
    assert omml_to_latex(_omath("<m:r><m:t>x</m:t></m:r>")) == "x"


def test_fraction():
    xml = _omath(
        "<m:f><m:num><m:r><m:t>a</m:t></m:r></m:num>"
        "<m:den><m:r><m:t>b</m:t></m:r></m:den></m:f>"
    )
    assert omml_to_latex(xml) == r"\frac{a}{b}"


def test_superscript():
    xml = _omath(
        "<m:sSup><m:e><m:r><m:t>x</m:t></m:r></m:e>"
        "<m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup>"
    )
    assert omml_to_latex(xml) == "{x}^{2}"


def test_subscript():
    xml = _omath(
        "<m:sSub><m:e><m:r><m:t>a</m:t></m:r></m:e>"
        "<m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub>"
    )
    assert omml_to_latex(xml) == "{a}_{i}"


def test_radical_default_index():
    xml = _omath("<m:rad><m:e><m:r><m:t>x</m:t></m:r></m:e></m:rad>")
    assert omml_to_latex(xml) == r"\sqrt{x}"


def test_nary_sum_with_limits():
    xml = _omath(
        "<m:nary><m:naryPr><m:chr m:val='∑'/></m:naryPr>"
        "<m:sub><m:r><m:t>i</m:t></m:r></m:sub>"
        "<m:sup><m:r><m:t>n</m:t></m:r></m:sup>"
        "<m:e><m:r><m:t>i</m:t></m:r></m:e></m:nary>"
    )
    out = omml_to_latex(xml)
    assert out.startswith(r"\sum_{i}^{n}")
    assert out.endswith("i")


def test_greek_symbol_mapped():
    out = omml_to_latex(_omath("<m:r><m:t>α + β</m:t></m:r>"))
    assert r"\alpha" in out and r"\beta" in out


def test_delimiter_parentheses():
    xml = _omath(
        "<m:d><m:e><m:r><m:t>x</m:t></m:r></m:e></m:d>"
    )
    out = omml_to_latex(xml)
    assert r"\left(" in out and r"\right)" in out


def test_empty_returns_none():
    assert omml_to_latex("") is None
    assert omml_to_latex("   ") is None
