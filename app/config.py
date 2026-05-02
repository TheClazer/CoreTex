from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    ENVIRONMENT: str = "development"
    MAX_FILE_SIZE_MB: int = 20
    RATE_LIMIT_PER_MINUTE: int = 10
    TEMP_URL_TTL_SECONDS: int = 300

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    class Config:
        env_file = ".env"

settings = Settings()
