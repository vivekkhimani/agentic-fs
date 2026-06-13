"""Runtime configuration (``AFS_*`` env vars).

Every swappable layer is selected here by a backend *name*, and every AWS-shaped
backend takes an optional ``endpoint_url`` override — which is the whole
plug-and-play story for S3-compatible storage (MinIO locally, Cloudflare R2,
Wasabi, Backblaze B2 in production) and DynamoDB Local.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AFS_", extra="ignore")

    region: str = "us-east-1"

    # --- object store ---
    object_store_backend: str = "s3"  # builtin "s3", or an afs.object_stores plugin name
    data_bucket: str = "agentic-fs-data"
    s3_endpoint_url: str | None = None  # set for MinIO / R2 / Wasabi / B2
    kms_key_arn: str | None = None  # SSE-KMS on PUT when set

    # --- catalog store (implemented in a later slice) ---
    catalog_backend: str = "dynamodb"  # builtin "dynamodb"/"postgres", or a plugin name
    catalog_table: str = "agentic-fs-catalog"
    dynamodb_endpoint_url: str | None = None  # set for DynamoDB Local


def load_settings() -> Settings:
    """Load settings from the environment."""
    return Settings()
