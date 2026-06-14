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
    # Comma-separated ladder of normalizer names, tried in order — the low-level
    # override. When unset, the ladder comes from `pipeline_preset` (or the `lite`
    # preset by default). Richer rungs are opt-in and need their extra (e.g.
    # "text_native,pdf,docx,docling" with afs-server[docling]).
    extraction_ladder: str = ""
    # A named, curated pipeline (see extraction.presets): lite | ocr | tables |
    # multimodal | full. A convenience over hand-listing rungs; an explicit
    # extraction_ladder overrides it.
    pipeline_preset: str | None = None

    # Extraction pipeline engine: "haystack" (configurable graph engine, ADR 0010 —
    # the default; needs the [haystack] extra, shipped in the worker image) or
    # "ladder" (built-in linear cascade — a slim, zero-dep "lite" mode). If
    # "haystack" is selected but the extra isn't installed, the ladder runs instead.
    pipeline_engine: str = "haystack"
    # Escalate a result whose reported confidence (0..1, e.g. OCR) is below this to
    # the next ladder rung. 0.0 (default) never gates on confidence; e.g. 0.6 sends
    # shaky Textract OCR on to a stronger rung (llm).
    extraction_min_confidence: float = 0.0

    @property
    def extraction_ladder_names(self) -> list[str]:
        if self.extraction_ladder.strip():
            return [name.strip() for name in self.extraction_ladder.split(",") if name.strip()]
        from afs_server.extraction.presets import preset_ladder

        return preset_ladder(self.pipeline_preset or "lite")

    # Level for the `afs_server` loggers (INFO surfaces extraction declines,
    # escalation, and per-document worker progress to CloudWatch). DEBUG to dig in,
    # WARNING to quiet down.
    log_level: str = "INFO"

    # --- auth ---
    # "dev" = a static local principal (NEVER for production); "oidc" = the OAuth
    # resource server (not yet implemented — fails closed until that slice lands).
    auth_mode: str = "dev"
    dev_tenant_id: str = "dev"
    dev_principal_id: str = "dev"


def load_settings() -> Settings:
    """Load settings from the environment."""
    return Settings()
