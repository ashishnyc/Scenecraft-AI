import boto3
from botocore.client import BaseClient
from functools import lru_cache

from app.core.config import get_settings


@lru_cache
def get_s3_client() -> BaseClient:
    settings = get_settings()
    kwargs = dict(
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )
    if settings.S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL

    return boto3.client("s3", **kwargs)
