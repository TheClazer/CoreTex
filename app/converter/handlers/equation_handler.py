"""OMML → LaTeX equation handler.

This is the ONLY place in the system where Pandoc is invoked. We pass the
raw OMML XML fragment for a single equation through Pandoc as a subprocess
and extract the resulting math string. Pandoc is never asked to convert a
whole document; the IR renderer handles structure.

Pandoc cannot parse a bare OMML fragment, so we wrap it in a minimal OOXML
``document.xml`` envelope and feed Pandoc a synthetic single-paragraph .docx.

Owner: P4. Reference: bible §2 Layer 4 + team distribution P4 note 1.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import List

from app.converter.ir_schema import EquationNode

logger = logging.getLogger(__name__)


_DOCUMENT_XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<w:body>
<w:p>{equation_xml}</w:p>
</w:body>
</w:document>
"""

_CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""


def _build_synthetic_docx(omml_xml: str) -> bytes:
    """Wrap a single OMML fragment in a valid one-paragraph .docx archive."""
    document_xml = _DOCUMENT_XML_TEMPLATE.format(equation_xml=omml_xml)
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
        zf.writestr("_rels/.rels", _RELS_XML)
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


_PANDOC_AVAILABLE: bool | None = None


def _pandoc_available() -> bool:
    global _PANDOC_AVAILABLE
    if _PANDOC_AVAILABLE is None:
        _PANDOC_AVAILABLE = shutil.which("pandoc") is not None
        if not _PANDOC_AVAILABLE:
            logger.warning("Pandoc not found on PATH; equations will be passed through verbatim.")
    return _PANDOC_AVAILABLE


def _strip_pandoc_wrappers(latex: str) -> str:
    """Pandoc emits e.g. ``\\[ x^2 \\]`` or ``\\(x^2\\)``; return raw math."""
    latex = latex.strip()
    # Display math
    m = re.match(r"^\\\[(.*?)\\\]$", latex, flags=re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.match(r"^\\\((.*?)\\\)$", latex, flags=re.DOTALL)
    if m:
        return m.group(1).strip()
    if latex.startswith("$$") and latex.endswith("$$") and len(latex) > 4:
        return latex[2:-2].strip()
    if latex.startswith("$") and latex.endswith("$") and len(latex) > 2:
        return latex[1:-1].strip()
    return latex


def convert_equation(omml_xml: str) -> str | None:
    """Convert a single OMML XML fragment to a LaTeX math string.

    Returns ``None`` if Pandoc is unavailable or fails.
    """
    if not _pandoc_available() or not omml_xml.strip():
        return None

    docx_bytes = _build_synthetic_docx(omml_xml)
    with tempfile.TemporaryDirectory() as td:
        in_path = Path(td) / "eq.docx"
        in_path.write_bytes(docx_bytes)
        try:
            result = subprocess.run(
                ["pandoc", "--from", "docx", "--to", "latex", str(in_path)],
                capture_output=True,
                timeout=15,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("Pandoc subprocess failed: %s", e)
            return None
    if result.returncode != 0:
        logger.warning("Pandoc returned %s: %s", result.returncode, result.stderr.decode(errors="replace"))
        return None
    return _strip_pandoc_wrappers(result.stdout.decode("utf-8", errors="replace"))


def hydrate_equations(equations: List[EquationNode]) -> List[str]:
    """Populate ``latex_string`` on each EquationNode in-place.

    Returns a list of warning strings for equations that failed to convert.
    """
    warnings: List[str] = []
    for idx, eq in enumerate(equations, start=1):
        if eq.latex_string:
            continue
        latex = convert_equation(eq.omml_xml)
        if latex is None:
            eq.latex_string = "?\\text{equation conversion failed}"
            warnings.append(
                f"Equation {idx} could not be converted from OMML; placeholder inserted."
            )
        else:
            eq.latex_string = latex
    return warnings
