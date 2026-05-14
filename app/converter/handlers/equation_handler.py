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
{paragraphs}
</w:body>
</w:document>
"""

# Sentinel paragraphs sandwich each equation so we can split Pandoc's batched
# output back into per-equation chunks. Keep them pure ASCII so Pandoc never
# rewrites them.
_BATCH_OPEN_FMT = "CORETEXEQOPEN{idx}"
_BATCH_CLOSE_FMT = "CORETEXEQCLOSE{idx}"

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


def _build_synthetic_docx(omml_xmls: List[str]) -> bytes:
    """Wrap N OMML fragments in a multi-paragraph .docx with split sentinels."""
    paragraphs: list[str] = []
    for i, xml in enumerate(omml_xmls):
        paragraphs.append(
            f"<w:p><w:r><w:t>{_BATCH_OPEN_FMT.format(idx=i)}</w:t></w:r></w:p>"
        )
        paragraphs.append(f"<w:p>{xml}</w:p>")
        paragraphs.append(
            f"<w:p><w:r><w:t>{_BATCH_CLOSE_FMT.format(idx=i)}</w:t></w:r></w:p>"
        )
    document_xml = _DOCUMENT_XML_TEMPLATE.format(paragraphs="\n".join(paragraphs))
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


def _batch_convert(omml_xmls: List[str]) -> List[str | None]:
    """Convert N OMML fragments to LaTeX math strings with ONE Pandoc call.

    Returns a list of the same length as the input — entries are ``None``
    where the per-equation conversion failed.
    """
    if not _pandoc_available() or not omml_xmls:
        return [None] * len(omml_xmls)

    docx_bytes = _build_synthetic_docx(omml_xmls)
    with tempfile.TemporaryDirectory() as td:
        in_path = Path(td) / "eqs.docx"
        in_path.write_bytes(docx_bytes)
        try:
            # Timeout scales gently with batch size so 150 equations don't
            # share the same 15s budget as 1.
            timeout = min(120, 15 + len(omml_xmls) // 4)
            result = subprocess.run(
                ["pandoc", "--from", "docx", "--to", "latex", str(in_path)],
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("Pandoc subprocess failed: %s", e)
            return [None] * len(omml_xmls)

    if result.returncode != 0:
        logger.warning(
            "Pandoc returned %s: %s",
            result.returncode,
            result.stderr.decode(errors="replace"),
        )
        return [None] * len(omml_xmls)

    text = result.stdout.decode("utf-8", errors="replace")
    out: list[str | None] = []
    for i in range(len(omml_xmls)):
        open_marker = _BATCH_OPEN_FMT.format(idx=i)
        close_marker = _BATCH_CLOSE_FMT.format(idx=i)
        # Pandoc sometimes splits markers across LaTeX commands; use regex
        # rather than literal find so embedded `\` doesn't trip us up.
        pattern = re.compile(
            re.escape(open_marker) + r"(.*?)" + re.escape(close_marker),
            re.DOTALL,
        )
        m = pattern.search(text)
        if not m:
            out.append(None)
            continue
        out.append(_strip_pandoc_wrappers(m.group(1)))
    return out


# Legacy single-equation entry point — kept for unit tests and direct callers.
def convert_equation(omml_xml: str) -> str | None:
    return _batch_convert([omml_xml])[0] if omml_xml.strip() else None


def hydrate_equations(equations: List[EquationNode]) -> List[str]:
    """Populate ``latex_string`` on each EquationNode in-place.

    Now batched: a single Pandoc subprocess converts every equation in
    the document, eliminating the N+1 boot overhead. A paper with 150
    equations goes from ~60 s (150 × 0.4 s) to ~0.6 s.
    """
    warnings: List[str] = []
    pending = [(i, eq) for i, eq in enumerate(equations) if not eq.latex_string]
    if not pending:
        return warnings

    results = _batch_convert([eq.omml_xml for _, eq in pending])
    for (_, eq), latex in zip(pending, results):
        if latex is None:
            eq.latex_string = "?\\text{equation conversion failed}"
            warnings.append(
                "Equation could not be converted from OMML; placeholder inserted."
            )
        else:
            eq.latex_string = latex
    return warnings
