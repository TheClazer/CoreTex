import logging
import pickle
import uuid
import zipfile
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, UploadFile, File, Query, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from rq.job import Job
from rq.exceptions import NoSuchJobError
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.queue.worker import redis_conn, conversion_queue, run_conversion
from app.converter.ir_schema import ConversionResult
from app.config import settings

# Configure router and local rate limiter
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
logger = logging.getLogger(__name__)


@router.post("/convert")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def convert_document(
    request: Request,
    file: UploadFile = File(...),
    template: Literal['article', 'ieee', 'acm', 'springer'] = Query('article')
):
    """
    Endpoint 1: Upload a .docx file and enqueue a conversion job.
    """
    logger.info(f"Received convert request from {request.client.host if request.client else 'unknown'}")

    # Stream into memory with a hard size cap so a hostile upload cannot OOM
    # the worker by sending an unbounded body before the size check fires.
    max_bytes = settings.max_file_size_bytes
    buffer = bytearray()
    chunk_size = 1 << 20  # 1 MiB
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum {settings.MAX_FILE_SIZE_MB} MB.",
            )
    contents = bytes(buffer)

    # Magic-byte check: .docx files are zip archives starting with PK\x03\x04
    if not contents.startswith(b'PK\x03\x04'):
        raise HTTPException(status_code=400, detail="Invalid file type. Must be a .docx file.")
        
    job_id = str(uuid.uuid4())
    
    # Enqueue job to RQ
    conversion_queue.enqueue(
        run_conversion,
        args=(job_id, contents, template),
        job_id=job_id
    )
    
    logger.info(f"Enqueued job {job_id} successfully.")
    return {"job_id": job_id, "status": "queued", "message": "Conversion started"}


@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Endpoint 2: Fetch the status of an RQ job from Redis.
    """
    logger.info(f"Status check for job {job_id}")
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except NoSuchJobError:
        return {"job_id": job_id, "status": "not_found"}
        
    response = {
        "job_id": job_id,
        "status": job.get_status()
    }
    
    if job.is_finished and job.result:
        res = job.result
        warnings_list = res.get("warnings", []) or []
        citation_count = sum(1 for w in warnings_list if "[CITATION]" in w)
        response["result_summary"] = {
            "has_images": res.get("has_images", False),
            "warning_count": len(warnings_list),
            "citation_count": citation_count,
            "compile_ok": res.get("compile_ok", False),
            "compile_error": res.get("compile_error"),
            "compile_error_line": res.get("compile_error_line"),
            "template": res.get("template"),
            "warnings": warnings_list,
        }
    elif job.is_failed:
        response["error_message"] = str(job.exc_info)

    return response


def zip_output(result: ConversionResult, figures: dict | None = None) -> BytesIO:
    """Bundle output.tex (and figures/) into an in-memory zip."""
    io_stream = BytesIO()
    with zipfile.ZipFile(io_stream, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('output.tex', result.latex_source)
        if figures:
            for name, data in figures.items():
                zf.writestr(f'figures/{name}', data)
        else:
            # Maintain folder presence in zip even when figures map is empty.
            zf.writestr('figures/.keep', '')
    io_stream.seek(0)
    return io_stream


@router.get("/download/{job_id}")
async def download_result(job_id: str):
    """
    Endpoint 3: Download the finished LaTeX conversion.
    """
    logger.info(f"Download request for job {job_id}")
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except NoSuchJobError:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if not job.is_finished:
        raise HTTPException(status_code=404, detail="Job is not finished")
        
    # Deserialise the result back into Pydantic schema
    result = ConversionResult(**job.result)

    # Append .tex / .zip extension so Overleaf's snip_uri import detects
    # the file type from the URL even if Content-Type negotiation fails.
    ext = "zip" if result.has_images else "tex"
    overleaf_header = {'X-Overleaf-Temp-URL': f"/temp/{job_id}.{ext}"}

    if result.has_images:
        # Cache the FULL zip (tex + figures) for Overleaf so its snip_uri
        # import gets the figures too. snip_uri supports both .tex and .zip.
        raw = redis_conn.get(f"figures:{job_id}")
        figures = pickle.loads(raw) if raw else {}
        zip_bytes = zip_output(result, figures).getvalue()
        redis_conn.setex(f"temp:{job_id}", settings.TEMP_URL_TTL_SECONDS, zip_bytes)
        redis_conn.setex(f"temp:{job_id}:type", settings.TEMP_URL_TTL_SECONDS, "zip")

        return StreamingResponse(
            BytesIO(zip_bytes),
            media_type='application/zip',
            headers={
                'Content-Disposition': 'attachment; filename="output.zip"',
                **overleaf_header,
            },
        )

    # Image-free path: cache the raw .tex for Overleaf.
    redis_conn.setex(f"temp:{job_id}", settings.TEMP_URL_TTL_SECONDS, result.latex_source)
    redis_conn.setex(f"temp:{job_id}:type", settings.TEMP_URL_TTL_SECONDS, "tex")
    return Response(
        content=result.latex_source,
        media_type='text/plain',
        headers={
            'Content-Disposition': 'attachment; filename="output.tex"',
            **overleaf_header,
        },
    )


@router.get("/temp/{job_id}.tex")
@router.get("/temp/{job_id}.zip")
@router.get("/temp/{job_id}")
async def get_temp_overleaf(job_id: str):
    """
    Endpoint 4: Public snip_uri target for Overleaf one-click import.

    Serves whatever was cached at /download time — either the raw .tex
    (for documents without images) or the full .zip (tex + figures/) so
    Overleaf's project import includes the assets.
    """
    logger.info(f"Temp file request for job {job_id}")
    cached = redis_conn.get(f"temp:{job_id}")
    if not cached:
        raise HTTPException(
            status_code=404,
            detail="Temp file expired. Re-run conversion to get a new Overleaf link.",
        )
    kind = redis_conn.get(f"temp:{job_id}:type")
    kind = kind.decode("ascii") if isinstance(kind, (bytes, bytearray)) else (kind or "tex")

    if kind == "zip":
        return Response(
            content=cached,
            media_type="application/zip",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": 'inline; filename="output.zip"',
            },
        )
    # .tex content must be served with a LaTeX-aware Content-Type and a
    # filename ending in .tex so Overleaf's snip_uri import recognises it.
    return Response(
        content=cached.decode("utf-8"),
        media_type="application/x-tex",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'inline; filename="output.tex"',
        },
    )
