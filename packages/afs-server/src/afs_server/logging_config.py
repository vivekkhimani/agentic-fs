"""Structured logging (structlog) — make the app's logs queryable.

Both entrypoints (the serving app factory and the worker handler) call
``configure_logging`` at startup. Without it, our ``logger.info(...)`` lines —
extraction declines, escalation, per-document worker progress — never appear:
Python's default level is WARNING, and on Lambda the runtime's root handler
suppresses INFO. (A silently-dropped INFO log is how a born-digital PDF degraded
to ``catalog_only`` unseen for hours.)

We emit **JSON** off a TTY (CloudWatch ships it; the fields are queryable in Logs
Insights) and a human **console** renderer on a TTY (local dev). Lambda's
advanced logging controls (JSON/level via the function config) only apply to
managed runtimes, not container images — so structured logging lives in code, the
one mechanism that works for the worker's container image, local dev, and ECS.

A **stdlib bridge** routes the existing ``logging.getLogger`` call sites (the
extraction pipeline, docling, auth — and noisy third parties like boto3/uvicorn)
through the same renderer, so output is consistent without rewriting every call.
New code can use ``structlog.get_logger(__name__)`` for structured key-value events.
"""

from __future__ import annotations

import logging
import sys

import structlog

_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog + the stdlib bridge at ``level`` (idempotent).

    Only the ``afs_server`` logger is raised to ``level``; the root stays at
    WARNING so boto3/botocore/uvicorn don't flood CloudWatch. Safe to call more
    than once (the worker calls it per invocation) — it always ends with exactly
    one root handler.
    """
    lvl = _LEVELS.get(level.strip().upper(), logging.INFO)

    # Shared by structlog-native events and stdlib-routed records, so both render
    # identically (level, logger name, ISO timestamp, exception/stack info).
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = (
        structlog.dev.ConsoleRenderer()
        if sys.stderr.isatty()
        else structlog.processors.JSONRenderer()
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers[:] = [handler]  # exactly one handler, even across repeated calls
    root.setLevel(logging.WARNING)
    logging.getLogger("afs_server").setLevel(lvl)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(lvl),
        cache_logger_on_first_use=True,
    )
