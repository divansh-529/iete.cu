"""File storage over the S3 API, so any provider works by changing the IETE_S3_* settings."""
from functools import lru_cache
from urllib.parse import quote

from app.core.config import settings
from app.core.errors import AppError

DOWNLOAD_LINK_SECONDS = 300


@lru_cache
def _client():
    import boto3
    from botocore.config import Config

    return boto3.client("s3", endpoint_url=settings.s3_endpoint_url, region_name=settings.s3_region,
                        aws_access_key_id=settings.s3_access_key_id,
                        aws_secret_access_key=settings.s3_secret_access_key,
                        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))


def ensure_configured() -> None:
    if not (settings.s3_endpoint_url and settings.s3_bucket and settings.s3_access_key_id
            and settings.s3_secret_access_key):
        raise AppError(503, "STORAGE_NOT_CONFIGURED", "File storage is not set up yet. Please tell the Chairperson.")


def put(key: str, content: bytes, mime_type: str) -> None:
    ensure_configured()
    _client().put_object(Bucket=settings.s3_bucket, Key=key, Body=content, ContentType=mime_type)


def presigned_url(key: str, filename: str, mime_type: str, inline: bool) -> str:
    ensure_configured()
    disposition = "inline" if inline else "attachment"
    return _client().generate_presigned_url("get_object", ExpiresIn=DOWNLOAD_LINK_SECONDS, Params={
        "Bucket": settings.s3_bucket, "Key": key, "ResponseContentType": mime_type,
        "ResponseContentDisposition": f"{disposition}; filename*=UTF-8''{quote(filename)}"})
