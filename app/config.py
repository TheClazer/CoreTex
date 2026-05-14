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
    # Comma-separated list of additional CORS origins, e.g.
    #   ALLOWED_ORIGINS=https://coretex.vercel.app,https://staging.coretex.app
    ALLOWED_ORIGINS: str = ""

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
