"""
RQ background worker for the Word to LaTeX Converter.
This module defines the job function and runs the worker process.
"""

import os
import logging
from redis import Redis
from rq import Queue, Worker

from app.converter.ir_schema import ConversionResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Redis Connection Settings
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# Initialize Redis and RQ Queue
redis_conn = Redis(host=REDIS_HOST, port=REDIS_PORT)
conversion_queue = Queue('conversions', connection=redis_conn)


def run_conversion(job_id: str, docx_bytes: bytes, template: str) -> dict:
    """
    Executes the Word to LaTeX conversion process.
    """
    logger.info(f"Job {job_id} started. Template: {template}")

    # TODO: Call parser.parse(docx_bytes) then renderer.render(ir_doc, template) once P2 and P3 complete their modules
    
    # Stub response matching ConversionResult schema
    stub_result = ConversionResult(
        job_id=job_id,
        latex_source="% STUB LaTeX SOURCE\n\\documentclass{article}\n\\begin{document}\nPlaceholder\n\\end{document}\n",
        has_images=False,
        warnings=["This is a stub result. The actual parser/renderer is not yet connected."],
        template=template,
        compile_ok=True,
        compile_error=None,
        compile_error_line=None,
        overleaf_temp_url=None
    )

    logger.info(f"Job {job_id} finished successfully.")
    
    return stub_result.model_dump()


if __name__ == '__main__':
    logger.info("Starting RQ worker for the 'conversions' queue...")
    # Start an RQ worker listening strictly on the 'conversions' queue
    worker = Worker([conversion_queue], connection=redis_conn)
    worker.work()
