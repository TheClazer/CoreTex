"""Single shared SlowAPI Limiter, Redis-backed in production.

Why a separate module: instantiating Limiter in both `main.py` and
`routes.py` produced TWO independent in-memory limiters that didn't share
state. Worse, the in-memory default doesn't survive a worker restart or
share state across multiple uvicorn workers, so the published rate limit
becomes meaningless under any real load. This module gives every caller
the same Limiter, and points it at Redis when a URL is available.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings


def _storage_uri() -> str:
    """Pick the right SlowAPI storage backend for the current environment."""
    if settings.REDIS_URL:
        # SlowAPI accepts a redis:// URL directly.
        return settings.REDIS_URL
    if settings.REDIS_HOST and settings.REDIS_HOST != "localhost":
        return f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
    # Local dev without Redis env vars: fall back to memory.
    # Acceptable because the dev machine isn't multi-process.
    return "memory://"


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_storage_uri(),
    strategy="fixed-window",
)
