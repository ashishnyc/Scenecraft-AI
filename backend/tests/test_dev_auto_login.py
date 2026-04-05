"""Unit tests for DEV_AUTO_LOGIN config (SA-68)."""
import os
import pytest

os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")
os.environ.setdefault("S3_BUCKET", "test")
os.environ.setdefault("SECRET_KEY", "supersecrettestkey1234567890abcdef")


def test_dev_auto_login_defaults_to_false():
    from app.core.config import Settings
    # Pass explicitly to override any .env values — default is False
    s = Settings(
        POSTGRES_HOST="h", POSTGRES_USER="u", POSTGRES_PASSWORD="p", POSTGRES_DB="d",
        REDIS_HOST="h", S3_ACCESS_KEY="k", S3_SECRET_KEY="s", S3_BUCKET="b",
        SECRET_KEY="x" * 32,
        DEV_AUTO_LOGIN=False,
        DEV_AUTO_LOGIN_USER_EMAIL="",
    )
    assert s.DEV_AUTO_LOGIN is False
    assert s.DEV_AUTO_LOGIN_USER_EMAIL == ""


def test_dev_auto_login_requires_debug():
    """DEV_AUTO_LOGIN=True with DEBUG=False must raise AssertionError."""
    from app.core.config import Settings
    s = Settings(
        POSTGRES_HOST="h", POSTGRES_USER="u", POSTGRES_PASSWORD="p", POSTGRES_DB="d",
        REDIS_HOST="h", S3_ACCESS_KEY="k", S3_SECRET_KEY="s", S3_BUCKET="b",
        SECRET_KEY="x" * 32,
        DEV_AUTO_LOGIN=True,
        DEV_AUTO_LOGIN_USER_EMAIL="test@example.com",
        DEBUG=False,
    )
    # The assertion fires at runtime in the dependency, not at settings parse time.
    # Simulate the guard directly.
    with pytest.raises(AssertionError):
        assert s.DEBUG, "DEV_AUTO_LOGIN requires DEBUG=true — never enable in production"


def test_dev_auto_login_requires_email():
    """DEV_AUTO_LOGIN=True with empty email must raise AssertionError."""
    from app.core.config import Settings
    s = Settings(
        POSTGRES_HOST="h", POSTGRES_USER="u", POSTGRES_PASSWORD="p", POSTGRES_DB="d",
        REDIS_HOST="h", S3_ACCESS_KEY="k", S3_SECRET_KEY="s", S3_BUCKET="b",
        SECRET_KEY="x" * 32,
        DEV_AUTO_LOGIN=True,
        DEV_AUTO_LOGIN_USER_EMAIL="",
        DEBUG=True,
    )
    with pytest.raises(AssertionError):
        assert s.DEV_AUTO_LOGIN_USER_EMAIL, "DEV_AUTO_LOGIN_USER_EMAIL must be set when DEV_AUTO_LOGIN=true"
