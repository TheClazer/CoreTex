from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Production: set REDIS_URL (Railway provides ${{Redis.REDIS_URL}}).
    # Local dev: REDIS_HOST + REDIS_PORT (no auth on the docker-compose Redis).
    REDIS_URL: str = ""
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    ENVIRONMENT: str = "development"
    MAX_FILE_SIZE_MB: int = 20
    RATE_LIMIT_PER_MINUTE: int = 10
    TEMP_URL_TTL_SECONDS: int = 300

    # ── Figure storage (v2: S3 / Cloudflare R2 offload) ─────────────────
    # "redis" (default) keeps figures in Redis with a short TTL — zero extra
    # infra, fine for the free tier. "s3" offloads them to S3/R2 so large or
    # numerous figures don't pressure Redis memory. S3 mode needs boto3 +
    # the S3_* settings; it degrades back to Redis if misconfigured.
    FIGURE_STORAGE: str = "redis"
    S3_BUCKET: str = ""
    S3_ENDPOINT_URL: str = ""  # set for Cloudflare R2 / MinIO; empty = AWS S3
    S3_REGION: str = "auto"
    S3_PREFIX: str = "figures"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    # Comma-separated list of additional CORS origins, e.g.
    #   ALLOWED_ORIGINS=https://coretex.vercel.app,https://staging.coretex.app
    ALLOWED_ORIGINS: str = ""

    # ── Postgres (Railway provides ${{Postgres.DATABASE_URL}}) ──────────
    # When empty, auth + history features are disabled and CoreTex still
    # works as a stateless converter. Setting it activates the user system.
    DATABASE_URL: str = ""

    # ── Auth ────────────────────────────────────────────────────────────
    # Use `openssl rand -hex 32` to generate. NEVER commit; set as env var.
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_HOURS: int = 24 * 7  # 7 days

    # OAuth provider credentials. Leave empty to disable that provider's
    # button on the frontend; the rest of the app keeps working.
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GITHUB_OAUTH_CLIENT_ID: str = ""
    GITHUB_OAUTH_CLIENT_SECRET: str = ""

    # Base URL the OAuth callback redirects to after provider sign-in.
    # In prod: https://<railway-domain>/auth/<provider>/callback
    OAUTH_REDIRECT_BASE: str = "http://localhost:8000"
    # Where the backend bounces the browser to after a successful OAuth
    # callback (frontend URL). Token is appended as ?token=...
    FRONTEND_URL: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @property
    def cors_origins(self) -> list[str]:
        base = ["http://localhost:5173"]
        extra = [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]
        return base + extra


settings = Settings()
