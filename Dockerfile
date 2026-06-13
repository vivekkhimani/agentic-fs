# syntax=docker/dockerfile:1.7
#
# agentic-fs API image. One image serves a Lambda Function URL (via the AWS
# Lambda Web Adapter) AND runs unchanged on Fargate/ECS or locally — see
# docs/decisions/0003-container-image.md.
#
# Security + size: multi-stage, slim Debian base (pinned), non-root runtime user,
# no secrets in any layer, deps installed from the committed lockfile only.

# ---------------------------------------------------------------------------
# Builder — resolve + install into a self-contained venv with uv (cached).
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

# Pinned uv, copied from its official image (no curl|sh).
COPY --from=ghcr.io/astral-sh/uv:0.9.13 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# 1) Dependency layer — only the manifests, so it caches until the lockfile or a
#    package's metadata changes (not on every source edit).
COPY pyproject.toml uv.lock ./
COPY packages/afs-core/pyproject.toml packages/afs-core/README.md ./packages/afs-core/
COPY packages/afs-server/pyproject.toml packages/afs-server/README.md ./packages/afs-server/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package afs-server

# 2) Project layer — install the workspace packages themselves (as built wheels,
#    not editable), so the runtime needs only the venv.
COPY packages/ ./packages/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package afs-server

# ---------------------------------------------------------------------------
# Runtime — minimal, non-root, web-adapter-enabled.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# AWS Lambda Web Adapter: forwards Lambda Function URL invocations (incl.
# response streaming) to the local ASGI server. Inert when not on Lambda.
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.0 \
    /lambda-adapter /opt/extensions/lambda-adapter

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    AWS_LWA_PORT=8080 \
    AWS_LWA_READINESS_CHECK_PATH=/v1/healthz

# Dedicated non-root user.
RUN groupadd --system afs && useradd --system --gid afs --uid 10001 afs

WORKDIR /app
COPY --from=builder --chown=afs:afs /app/.venv /app/.venv

USER afs
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/v1/healthz').status==200 else 1)"

CMD ["uvicorn", "afs_server.app:app", "--host", "0.0.0.0", "--port", "8080"]
