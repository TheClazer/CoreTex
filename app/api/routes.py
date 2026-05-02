import logging
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
    
    contents = await file.read()
    
    # Validation step 1: Size limit
    if len(contents) > settings.max_file_size_bytes:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum {settings.MAX_FILE_SIZE_MB} MB.")
        
    # Validation step 2: Magic bytes for zip-based .docx
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
        response["result_summary"] = {
            "has_images": res.get("has_images", False),
            "warning_count": len(res.get("warnings", [])),
            "compile_ok": res.get("compile_ok", False)
        }
    elif job.is_failed:
        response["error_message"] = str(job.exc_info)
        
    return response


def zip_output(result: ConversionResult) -> BytesIO:
    """Helper to zip output.tex and figures."""
    io_stream = BytesIO()
    with zipfile.ZipFile(io_stream, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('output.tex', result.latex_source)
        # Stub for the figures subfolder
        zf.writestr('figures/', '')
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
    
    if result.has_images:
        zip_io = zip_output(result)
        return StreamingResponse(
            zip_io,
            media_type='application/zip',
            headers={'Content-Disposition': 'attachment; filename="output.zip"'}
        )
    else:
        # Store in Redis for Overleaf integration with TTL from settings
        redis_conn.setex(f"temp:{job_id}", settings.TEMP_URL_TTL_SECONDS, result.latex_source)
        
        headers = {
            'Content-Disposition': 'attachment; filename="output.tex"',
            'X-Overleaf-Temp-URL': f"/temp/{job_id}"
        }
        return Response(
            content=result.latex_source,
            media_type='text/plain',
            headers=headers
        )


@router.get("/temp/{job_id}")
async def get_temp_overleaf(job_id: str):
    """
    Endpoint 4: Fetch temp .tex file for Overleaf integration.
    """
    logger.info(f"Temp file request for job {job_id}")
    latex_source_bytes = redis_conn.get(f"temp:{job_id}")
    
    if not latex_source_bytes:
        raise HTTPException(
            status_code=404, 
            detail="Temp file expired. Re-run conversion to get a new Overleaf link."
        )
        
    latex_source = latex_source_bytes.decode('utf-8')
    
    return Response(
        content=latex_source,
        media_type='text/plain',
        headers={'Cache-Control': 'no-store'}
    )
