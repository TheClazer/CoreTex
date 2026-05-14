import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.routes import router
from app.config import settings

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title='Word to LaTeX Converter',
    version='1.0.0',
    description='A high-fidelity Word (.docx) to LaTeX converter with support for equations, tables, and images.'
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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Overleaf-Temp-URL"],
)

# Include API routes
app.include_router(router)

@app.get("/")
async def root():
    """Service status health check."""
    return {"status": "ok", "service": "word-to-latex"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
