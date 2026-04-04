"""Unit tests for config validation (SC-1)."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings


VALID_ENV = dict(
    POSTGRES_HOST="localhost",
    POSTGRES_USER="scenecraft",
    POSTGRES_PASSWORD="secret",
    POSTGRES_DB="scenecraft_db",
    REDIS_HOST="localhost",
    S3_ACCESS_KEY="minioadmin",
    S3_SECRET_KEY="minioadmin",
    S3_BUCKET="scenecraft",
    SECRET_KEY="supersecretkey",
)


def test_valid_config_passes():
    settings = Settings(**VALID_ENV)
    assert settings.POSTGRES_PORT == 5432
    assert settings.REDIS_PORT == 6379
    assert settings.S3_REGION == "us-east-1"
    assert settings.DEBUG is False


def test_database_url_format():
    settings = Settings(**VALID_ENV)
    assert settings.database_url == (
        "postgresql+asyncpg://scenecraft:secret@localhost:5432/scenecraft_db"
    )


def test_redis_url_without_password():
    settings = Settings(**VALID_ENV)
    assert settings.redis_url == "redis://localhost:6379/0"


def test_redis_url_with_password():
    settings = Settings(**{**VALID_ENV, "REDIS_PASSWORD": "redispass"})
    assert settings.redis_url == "redis://:redispass@localhost:6379/0"


def test_missing_required_field_raises():
    env = {k: v for k, v in VALID_ENV.items() if k != "POSTGRES_HOST"}
    with pytest.raises(ValidationError) as exc_info:
        Settings(**env)
    assert "POSTGRES_HOST" in str(exc_info.value)


@pytest.mark.parametrize("missing_field", [
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "REDIS_HOST",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "S3_BUCKET",
    "SECRET_KEY",
])
def test_all_required_fields(missing_field):
    env = {k: v for k, v in VALID_ENV.items() if k != missing_field}
    with pytest.raises(ValidationError):
        Settings(**env)


def test_s3_endpoint_url_defaults_to_empty():
    settings = Settings(**VALID_ENV)
    assert settings.S3_ENDPOINT_URL == ""


def test_custom_postgres_port():
    settings = Settings(**{**VALID_ENV, "POSTGRES_PORT": 5433})
    assert settings.POSTGRES_PORT == 5433
    assert "5433" in settings.database_url
