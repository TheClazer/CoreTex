r"""Direct OMML → LaTeX converter (v2 roadmap: direct OMML parser).

A dependency-free fallback for the Pandoc-based equation handler. When Pandoc
is not on PATH (or fails), this walks the OMML (Office Math Markup Language)
tree itself and emits LaTeX math. It covers the constructs that actually show
up in academic Word documents:

    fractions, super/subscripts, radicals, delimiters, n-ary operators
    (sum / product / integral with limits), functions, accents, bars,
    groups, matrices, and the common Unicode math symbols / Greek letters.

It is intentionally best-effort: unknown elements degrade to their text
content rather than failing. Pandoc remains the primary, higher-fidelity path
(see equation_handler); this guarantees equations still convert on a host
without Pandoc instead of becoming "equation conversion failed" placeholders.
"""

from __future__ import annotations

import logging
from typing import Optional

from lxml import etree

logger = logging.getLogger(__name__)

_M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def _m(tag: str) -> str:
    return f"{{{_M_NS}}}{tag}"


def _val(elem, attr: str) -> Optional[str]:
    """Read an m:val attribute off a property child element."""
    if elem is None:
        return None
    return elem.get(_m("val"))


# Unicode math glyphs → bare LaTeX commands (we are already inside math mode,
# so unlike the text escape layer these are NOT wrapped in $...$).
_SYMBOLS: dict[str, str] = {
    # Greek lowercase
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\epsilon", "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta",
    "ι": r"\iota", "κ": r"\kappa", "λ": r"\lambda", "μ": r"\mu",
    "ν": r"\nu", "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho",
    "σ": r"\sigma", "τ": r"\tau", "υ": r"\upsilon", "φ": r"\phi",
    "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega", "ϕ": r"\varphi",
    # Greek uppercase
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda",
    "Ξ": r"\Xi", "Π": r"\Pi", "Σ": r"\Sigma", "Φ": r"\Phi",
    "Ψ": r"\Psi", "Ω": r"\Omega",
    # Operators / relations
    "×": r"\times", "÷": r"\div", "±": r"\pm", "∓": r"\mp",
    "·": r"\cdot", "∗": r"\ast", "≤": r"\leq", "≥": r"\geq",
    "≠": r"\neq", "≈": r"\approx", "≡": r"\equiv", "∝": r"\propto",
    "∞": r"\infty", "∂": r"\partial", "∇": r"\nabla", "∫": r"\int",
    "∑": r"\sum", "∏": r"\prod", "√": r"\sqrt", "→": r"\to",
    "←": r"\leftarrow", "⇒": r"\Rightarrow", "⇔": r"\Leftrightarrow",
    "∈": r"\in", "∉": r"\notin", "⊂": r"\subset", "⊆": r"\subseteq",
    "∪": r"\cup", "∩": r"\cap", "∅": r"\emptyset", "∀": r"\forall",
    "∃": r"\exists", "¬": r"\neg", "∧": r"\land", "∨": r"\lor",
    "−": "-", "⋅": r"\cdot", "…": r"\dots", "⋯": r"\cdots",
}

# n-ary operator chr → LaTeX command (default sum if unspecified).
_NARY = {
    "∑": r"\sum", "∏": r"\prod", "∫": r"\int", "∬": r"\iint",
    "∭": r"\iiint", "∮": r"\oint", "⋃": r"\bigcup", "⋂": r"\bigcap",
    "⋀": r"\bigwedge", "⋁": r"\bigvee", "⨁": r"\bigoplus",
}

# Accent chr → LaTeX accent command.
_ACCENTS = {
    "̂": r"\hat", "̃": r"\tilde", "̄": r"\bar", "̇": r"\dot",
    "̈": r"\ddot", "⃗": r"\vec", "́": r"\acute", "̀": r"\grave",
}


def _map_text(text: str) -> str:
    """Translate a math text run, mapping Unicode glyphs to LaTeX."""
    out: list[str] = []
    for ch in text:
        if ch in _SYMBOLS:
            out.append(_SYMBOLS[ch] + " ")
        else:
            out.append(ch)
    return "".join(out)


def _children(elem) -> list:
    return [c for c in elem if isinstance(c.tag, str)]


def _convert(elem) -> str:
    """Recursively convert an OMML element to a LaTeX fragment."""
    if elem is None:
        return ""
    tag = etree.QName(elem).localname

    if tag in ("oMath", "oMathPara"):
        return "".join(_convert(c) for c in _children(elem))

    if tag == "r":  # math run
        parts = []
        for t in elem.findall(_m("t")):
            parts.append(_map_text(t.text or ""))
        return "".join(parts)

    if tag == "t":
        return _map_text(elem.text or "")

    if tag == "f":  # fraction
        num = _convert(elem.find(_m("num")))
        den = _convert(elem.find(_m("den")))
        return f"\\frac{{{num}}}{{{den}}}"

    if tag == "sSup":  # superscript
        base = _convert(elem.find(_m("e")))
        sup = _convert(elem.find(_m("sup")))
        return f"{{{base}}}^{{{sup}}}"

    if tag == "sSub":  # subscript
        base = _convert(elem.find(_m("e")))
        sub = _convert(elem.find(_m("sub")))
        return f"{{{base}}}_{{{sub}}}"

    if tag == "sSubSup":  # both
        base = _convert(elem.find(_m("e")))
        sub = _convert(elem.find(_m("sub")))
        sup = _convert(elem.find(_m("sup")))
        return f"{{{base}}}_{{{sub}}}^{{{sup}}}"

    if tag == "rad":  # radical
        deg_el = elem.find(_m("deg"))
        e = _convert(elem.find(_m("e")))
        deg = _convert(deg_el) if deg_el is not None and _children(deg_el) else ""
        return f"\\sqrt[{deg}]{{{e}}}" if deg else f"\\sqrt{{{e}}}"

    if tag == "d":  # delimiter (parentheses, brackets, …)
        dPr = elem.find(_m("dPr"))
        beg, end = "(", ")"
        if dPr is not None:
            beg = _val(dPr.find(_m("begChr")), "val") or beg
            end = _val(dPr.find(_m("endChr")), "val") or end
        inner = "".join(_convert(e) for e in elem.findall(_m("e")))
        return f"\\left{_delim(beg)} {inner} \\right{_delim(end)}"

    if tag == "nary":  # n-ary operator (sum, integral, product …)
        naryPr = elem.find(_m("naryPr"))
        chr_ = _val(naryPr.find(_m("chr")), "val") if naryPr is not None else None
        op = _NARY.get(chr_ or "∑", r"\sum")
        sub = _convert(elem.find(_m("sub")))
        sup = _convert(elem.find(_m("sup")))
        body = _convert(elem.find(_m("e")))
        limits = ""
        if sub:
            limits += f"_{{{sub}}}"
        if sup:
            limits += f"^{{{sup}}}"
        return f"{op}{limits} {body}"

    if tag == "func":  # named function (sin, lim, …)
        fname = _convert(elem.find(_m("fName")))
        e = _convert(elem.find(_m("e")))
        return f"{fname}{{{e}}}" if fname.startswith("\\") else f"\\operatorname{{{fname}}}({e})"

    if tag == "limLow":  # lower limit (e.g. lim_{x\to 0})
        base = _convert(elem.find(_m("e")))
        lim = _convert(elem.find(_m("lim")))
        return f"{base}_{{{lim}}}"

    if tag == "limUpp":
        base = _convert(elem.find(_m("e")))
        lim = _convert(elem.find(_m("lim")))
        return f"{base}^{{{lim}}}"

    if tag == "acc":  # accent
        accPr = elem.find(_m("accPr"))
        chr_ = _val(accPr.find(_m("chr")), "val") if accPr is not None else "̂"
        cmd = _ACCENTS.get(chr_ or "̂", r"\hat")
        e = _convert(elem.find(_m("e")))
        return f"{cmd}{{{e}}}"

    if tag == "bar":  # overline / underline bar
        e = _convert(elem.find(_m("e")))
        return f"\\overline{{{e}}}"

    if tag == "groupChr":  # grouping character (e.g. underbrace)
        e = _convert(elem.find(_m("e")))
        return f"{{{e}}}"

    if tag == "m":  # matrix
        rows = []
        for mr in elem.findall(_m("mr")):
            cells = [_convert(c) for c in mr.findall(_m("e"))]
            rows.append(" & ".join(cells))
        body = " \\\\ ".join(rows)
        return f"\\begin{{matrix}} {body} \\end{{matrix}}"

    if tag in ("e", "num", "den", "sup", "sub", "deg", "lim", "fName"):
        # Container elements: convert their children inline.
        return "".join(_convert(c) for c in _children(elem))

    # Unknown element: recurse into children so we don't drop content.
    return "".join(_convert(c) for c in _children(elem))


def _delim(chr_: str) -> str:
    """Map a delimiter character to its LaTeX \\left/\\right token."""
    mapping = {
        "(": "(", ")": ")", "[": "[", "]": "]",
        "{": r"\{", "}": r"\}", "|": "|", "‖": r"\|",
        "⟨": r"\langle", "⟩": r"\rangle", "": ".",
    }
    return mapping.get(chr_, chr_ or ".")


def omml_to_latex(omml_xml: str) -> Optional[str]:
    """Convert one OMML fragment (as XML text) to a LaTeX math string.

    Returns the LaTeX body (without surrounding ``$``) or None if the fragment
    can't be parsed at all.
    """
    if not omml_xml or not omml_xml.strip():
        return None
    try:
        root = etree.fromstring(omml_xml.encode("utf-8"))
    except etree.XMLSyntaxError as e:  # pragma: no cover - defensive
        logger.warning("OMML did not parse: %s", e)
        return None
    latex = _convert(root).strip()
    # Collapse runs of whitespace the symbol-spacing introduced.
    latex = " ".join(latex.split())
    return latex or None
