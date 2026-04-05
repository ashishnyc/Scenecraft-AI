from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # PostgreSQL
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    # Redis
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""

    # S3 / MinIO
    S3_ENDPOINT_URL: str = ""          # empty = AWS S3; set for MinIO
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_BUCKET: str
    S3_REGION: str = "us-east-1"

    # Google OAuth2
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/callback"

    # YouTube Data API
    YOUTUBE_API_KEY: str = ""

    # Reddit API (PRAW)
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""

    # NewsAPI
    NEWS_API_KEY: str = ""

    # Anthropic (Claude)
    ANTHROPIC_API_KEY: str = ""

    # Voice synthesis (SA-25)
    ELEVENLABS_API_KEY: str = ""
    FISH_AUDIO_API_KEY: str = ""

    # Qdrant vector DB
    QDRANT_URL: str = ""        # empty = in-memory
    QDRANT_API_KEY: str = ""

    # Originality threshold (cosine similarity 0-1; above this = too similar)
    ORIGINALITY_THRESHOLD: float = 0.85

    # Copyright similarity threshold for script scans (stage 4 of script pipeline)
    COPYRIGHT_THRESHOLD: float = 0.80

    # JWT
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:5174"]

    # Dev bypass — never enable in production
    DEV_AUTO_LOGIN: bool = False
    DEV_AUTO_LOGIN_USER_EMAIL: str = ""

    # App
    SECRET_KEY: str
    DEBUG: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def redis_url(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
