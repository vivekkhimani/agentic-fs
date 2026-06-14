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

    # --- catalog store ---
    catalog_backend: str = "dynamodb"  # builtin "dynamodb"/"postgres", or a plugin name
    catalog_table: str = "agentic-fs-catalog"
    dynamodb_endpoint_url: str | None = None  # set for DynamoDB Local

    # --- extraction ---
    # "inline" runs extraction synchronously in the request (text_native, no extra
    # infra); "async" stores the doc + a `pending` row and lets the extractor
    # worker complete it off an S3 event (ADR 0009). Default inline.
    extraction_mode: str = "inline"
    # Comma-separated ladder of normalizer names, tried in order. The default is
    # the lightweight, always-available rungs (pypdfium2/python-docx are base
    # deps), so born-digital PDFs and Word docs extract inline with no extras —
    # keep this in sync with extraction.DEFAULT_LADDER. Richer rungs are opt-in
    # and need their extra (e.g. "text_native,pdf,docx,docling" with
    # afs-server[docling]).
    extraction_ladder: str = "text_native,pdf,docx"

    @property
    def extraction_ladder_names(self) -> list[str]:
        return [name.strip() for name in self.extraction_ladder.split(",") if name.strip()]

    # --- auth ---
    # "dev" = a static local principal (NEVER for production); "oidc" = the OAuth
    # resource server (not yet implemented — fails closed until that slice lands).
    auth_mode: str = "dev"
    dev_tenant_id: str = "dev"
    dev_principal_id: str = "dev"


def load_settings() -> Settings:
    """Load settings from the environment."""
    return Settings()
