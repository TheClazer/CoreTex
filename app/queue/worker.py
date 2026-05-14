"""RQ background worker for the Word → LaTeX Converter.

This module owns the conversion job function and the worker entrypoint.
The job orchestrates the full pipeline:
    parse(docx_bytes) → hydrate equations → compress images
                     → render(IR, template) → pdflatex compile check
                     → return ConversionResult
"""

from __future__ import annotations

import logging
from typing import Any, List

from redis import Redis
from rq import Queue, Worker

from app.config import settings
from app.converter.compile_check import compile_check, pdflatex_available
from app.converter.handlers.equation_handler import hydrate_equations
from app.converter.handlers.image_handler import process_images
from app.converter.ir_schema import (
    ConversionResult,
    EquationNode,
    ImageNode,
)
from app.converter.parser import parse_docx
from app.converter.renderer import render

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Prefer REDIS_URL when present (production, includes password + scheme).
# Fall back to host/port for local docker-compose dev.
if settings.REDIS_URL:
    redis_conn = Redis.from_url(settings.REDIS_URL)
else:
    redis_conn = Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
conversion_queue = Queue("conversions", connection=redis_conn)


def _collect_image_nodes(nodes: List[Any]) -> List[ImageNode]:
    return [n for n in nodes if isinstance(n, ImageNode)]


def _collect_equation_nodes(nodes: List[Any]) -> List[EquationNode]:
    return [n for n in nodes if isinstance(n, EquationNode)]


def run_conversion(job_id: str, docx_bytes: bytes, template: str) -> dict:
    """Execute the full Word → LaTeX pipeline for one upload.

    The function is queued by FastAPI's POST /convert route and runs in
    an RQ worker process. The dict it returns is what GET /status and
    GET /download read back from Redis.
    """
    logger.info("Job %s starting (template=%s, %.1f KB)", job_id, template, len(docx_bytes) / 1024)

    try:
        ir_doc = parse_docx(docx_bytes)
    except ValueError as e:
        logger.error("Parse failed for job %s: %s", job_id, e)
        return ConversionResult(
            job_id=job_id,
            latex_source="",
            has_images=False,
            warnings=[f"Parse failed: {e}"],
            template=template,
            compile_ok=False,
            compile_error=str(e),
        ).model_dump()

    warnings: List[str] = list(ir_doc.warnings)

    # Hydrate equations through Pandoc.
    eq_nodes = _collect_equation_nodes(ir_doc.nodes)
    if eq_nodes:
        warnings.extend(hydrate_equations(eq_nodes))

    # Compress images + collect figure payloads.
    img_nodes = _collect_image_nodes(ir_doc.nodes)
    figures = process_images(img_nodes) if img_nodes else {}

    # Persist figures alongside the job so /download can stream them into the
    # zip. We store each file as a separate raw-byte key (no pickle) and
    # maintain a manifest of filenames. This avoids:
    #   * pickle deserialisation risk if Redis is ever compromised
    #   * the single-key bottleneck of one giant blob
    # All keys share the same short TTL as the Overleaf temp URL.
    if figures:
        ttl = settings.TEMP_URL_TTL_SECONDS
        manifest = "\n".join(figures.keys()).encode("utf-8")
        redis_conn.setex(f"figures:{job_id}:manifest", ttl, manifest)
        for name, data in figures.items():
            redis_conn.setex(f"figures:{job_id}:f:{name}", ttl, data)

    # Render to LaTeX.
    latex_source, render_warnings = render(ir_doc, template=template)
    warnings.extend(render_warnings)

    # Compile check (skipped gracefully when pdflatex isn't on PATH).
    if pdflatex_available():
        ok, err_msg, err_line = compile_check(latex_source, figures)
    else:
        ok, err_msg, err_line = True, None, None
        warnings.append("pdflatex not available in this environment; compile check skipped.")

    result = ConversionResult(
        job_id=job_id,
        latex_source=latex_source,
        has_images=bool(img_nodes),
        warnings=warnings,
        template=template,
        compile_ok=ok,
        compile_error=err_msg,
        compile_error_line=err_line,
    )
    logger.info(
        "Job %s done (compile_ok=%s, warnings=%d, images=%d)",
        job_id, ok, len(warnings), len(img_nodes),
    )
    return result.model_dump()


if __name__ == "__main__":
    logger.info("Starting RQ worker for the 'conversions' queue …")
    worker = Worker([conversion_queue], connection=redis_conn)
    worker.work(with_scheduler=False)
