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
    # Path to a routing YAML (ADR 0010): per-content-type ladders (see
    # extraction.routing). When set, it takes precedence over ladder/preset.
    pipeline_file: str | None = None

    # Extraction pipeline engine: "haystack" (configurable graph engine, ADR 0010 —
    # the default; needs the [haystack] extra, shipped in the worker image) or
    # "ladder" (built-in linear cascade — a slim, zero-dep "lite" mode). If
    # "haystack" is selected but the extra isn't installed, the ladder runs instead.
    pipeline_engine: str = "haystack"
    # Escalate a result whose reported confidence (0..1, e.g. OCR) is below this to
    # the next ladder rung. 0.0 (default) never gates on confidence; e.g. 0.6 sends
    # shaky Textract OCR on to a stronger rung (llm).
    extraction_min_confidence: float = 0.0

    # --- reconciler (heal catalog drift from S3) ---
    # The extract SQS queue the reconciler enqueues drift onto (the worker drains it).
    extract_queue_url: str | None = None
    # Don't tombstone an orphaned row updated within this window — race guard.
    reconcile_grace_seconds: int = 900

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

    # --- MCP tool middleware ---
    # A uniform per-call output budget (ADR 0012): the middleware rejects any tool
    # result whose serialized size exceeds this, with a "narrow your query" error —
    # an output-size safety net above each tool's own caps, so a misbehaving plugin
    # tool can't blow the agent's context window. 0 disables the net.
    tool_max_result_bytes: int = 262_144  # 256 KiB

    # --- auth ---
    # "dev" = a static local principal (NEVER for production); "oidc" = the OAuth
    # 2.1 resource server (ADR 0013) — validate bearer JWTs from your own IdP.
    auth_mode: str = "dev"
    dev_tenant_id: str = "dev"
    dev_principal_id: str = "dev"

    # --- auth: OIDC resource server (ADR 0013, when auth_mode="oidc") ---
    # We validate tokens against your IdP's keys; we never issue them ("bring your
    # own IdP"). Supply a JWKS URI (production) or a static PEM public key (the
    # offline "static-jwt" mode, also what the unit tests mint against). `issuer`
    # and `audience` (RFC 8707 resource binding) are validated when set.
    oidc_issuer: str | None = None
    oidc_jwks_uri: str | None = None
    oidc_audience: str | None = None
    oidc_algorithm: str = "RS256"
    oidc_public_key: str | None = None  # static-jwt mode (PEM)
    # Claim → TenantContext mapping. Defaults fit the common case; override the
    # names that differ per IdP (e.g. WorkOS tenant=org_id, Cognito=custom:tenant_id).
    # Scopes are TRUSTED FROM THE TOKEN (no role mapping). An absent tenant claim
    # falls back to oidc_default_tenant.
    oidc_principal_claim: str = "sub"
    oidc_tenant_claim: str = "tenant_id"
    oidc_default_tenant: str | None = None
    oidc_scopes_claim: str = "scope"
    # Namespaces are the data boundary, so an absent namespaces claim FAILS SAFE
    # (deny all). Set this to opt a deployment into a default when the claim is
    # absent: "*" = tenant-wide (single-tenant convenience), or a comma/space list
    # of namespaces. The claim itself may also be "*" to grant tenant-wide per token.
    oidc_namespaces_claim: str = "afs_namespaces"
    oidc_default_namespaces: str | None = None


def load_settings() -> Settings:
    """Load settings from the environment."""
    return Settings()
