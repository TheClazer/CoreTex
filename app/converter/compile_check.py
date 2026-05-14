"""TeX Live compile check.

Runs pdflatex inside the container against the generated .tex file and
parses errors with their LaTeX line numbers. The worker calls this after
rendering; when pdflatex is unavailable (e.g. local Windows dev outside
Docker), the check is skipped gracefully.

Owner: P4 (in collaboration with P3). Reference: bible §2 Layer 7.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_ERROR_LINE_RE = re.compile(r"^l\.(\d+)\s", re.MULTILINE)
_ERROR_MSG_RE = re.compile(r"^! (.+)$", re.MULTILINE)


def pdflatex_available() -> bool:
    return shutil.which("pdflatex") is not None


def compile_check(
    latex_source: str,
    figures: Optional[Dict[str, bytes]] = None,
    timeout: int = 60,
) -> Tuple[bool, Optional[str], Optional[int]]:
    """Run pdflatex once and report success/failure.

    Returns ``(compile_ok, error_message, error_line)``. If pdflatex is not
    on PATH, returns ``(True, None, None)`` and lets the caller note that
    the check was skipped via a separate warning.
    """
    if not pdflatex_available():
        logger.info("pdflatex not available; skipping compile check.")
        return True, None, None

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        tex_file = work / "doc.tex"
        tex_file.write_text(latex_source, encoding="utf-8")

        if figures:
            fig_dir = work / "figures"
            fig_dir.mkdir(exist_ok=True)
            for name, data in figures.items():
                (fig_dir / name).write_bytes(data)

        try:
            result = subprocess.run(
                [
                    "pdflatex",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-output-directory",
                    str(work),
                    str(tex_file),
                ],
                capture_output=True,
                timeout=timeout,
                cwd=work,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "pdflatex timed out", None

        log = (result.stdout or b"").decode("utf-8", errors="replace")
        if result.returncode == 0 and (work / "doc.pdf").exists():
            return True, None, None

        # Extract first error message + line number from the log.
        msg_match = _ERROR_MSG_RE.search(log)
        line_match = _ERROR_LINE_RE.search(log)
        message = msg_match.group(1).strip() if msg_match else "Unknown pdflatex failure"
        line = int(line_match.group(1)) if line_match else None
        return False, message, line
