import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.auth_routes import router as auth_router
from app.api.history_routes import router as history_router
from app.api.routes import router
from app.config import settings
from app.db import create_all, db_enabled
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CoreTex — Word to LaTeX Converter",
    version="1.2.0",
    description=(
        "A high-fidelity Word (.docx) to LaTeX converter with support for "
        "equations, tables, images, user accounts, and conversion history."
    ),
)

# Add SlowAPI rate limiting to state and middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS configuration.
# Explicit allowlist — never use "*" alongside allow_credentials=True
# (browsers reject that combination per the CORS spec).
# Add production origins via the ALLOWED_ORIGINS env var (comma-separated).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Overleaf-Temp-URL"],
)

# Core converter routes.
app.include_router(router)

# Auth + history routes — both no-ops without DATABASE_URL configured;
# their handlers return 503 in that case rather than 404, so the frontend
# can show a clean "auth disabled" state.
app.include_router(auth_router)
app.include_router(history_router)


@app.on_event("startup")
def _bootstrap_db() -> None:
    """Run table creation once the app comes up.

    For zero-downtime deploys this is fine because the model schema is
    additive in v1 — every new table has CREATE TABLE IF NOT EXISTS
    semantics via SQLAlchemy. For breaking schema changes in the future,
    swap this for Alembic migrations.
    """
    if db_enabled():
        try:
            create_all()
        except Exception as e:  # pragma: no cover - DB issues at startup
            logger.exception("Failed to bootstrap database tables: %s", e)


@app.get("/")
async def root():
    """Service status health check."""
    return {
        "status": "ok",
        "service": "word-to-latex",
        "version": app.version,
        "features": {
            "auth": db_enabled() and bool(settings.JWT_SECRET),
            "history": db_enabled(),
            "google_oauth": bool(settings.GOOGLE_OAUTH_CLIENT_ID),
            "github_oauth": bool(settings.GITHUB_OAUTH_CLIENT_ID),
        },
    }


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
