"""Async extractor worker (ADR 0009).

An S3 object-created event (via EventBridge → SQS) arrives; the worker reverses
the object key to ``tenant/namespace/path`` and runs the extraction pipeline
(which, in the worker image, includes ``docling``). It is the Lambda handler for
the extractor function — separate from the serving app so the heavy ML deps never
touch the request path.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import unquote_plus

import structlog

from afs_core import keys
from afs_server.extraction import build_pipeline
from afs_server.logging_config import configure_logging
from afs_server.services import IngestService
from afs_server.settings import load_settings
from afs_server.stores import get_catalog_store, get_object_store

logger = structlog.get_logger("afs_server.worker")


def object_keys_from_event(event: dict[str, Any]) -> list[str]:
    """Pull S3 object keys from an SQS batch.

    Each SQS record's ``body`` is an S3 event — either an EventBridge "Object
    Created" event (``detail.object.key``) or a direct S3 notification
    (``Records[].s3.object.key``). Both shapes are handled.
    """
    out: list[str] = []
    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
        except (KeyError, json.JSONDecodeError):
            logger.warning("skipping malformed SQS record", message_id=record.get("messageId"))
            continue
        if isinstance(body.get("detail"), dict):  # EventBridge
            key = body["detail"].get("object", {}).get("key")
            if key:
                out.append(unquote_plus(key))
        for s3_record in body.get("Records", []):  # direct S3 notification
            key = s3_record.get("s3", {}).get("object", {}).get("key")
            if key:
                out.append(unquote_plus(key))
    return out


async def process_keys(ingest: IngestService, object_keys: list[str]) -> int:
    """Extract each indexable original key. Returns how many were processed."""
    processed = 0
    for key in object_keys:
        parsed = keys.parse_key(key)
        if parsed is None or not keys.is_indexable(key) or not (parsed.namespace and parsed.path):
            logger.info("skipping non-original key", key=key)
            continue
        await ingest.extract_object(parsed.tenant_id, parsed.namespace, parsed.path)
        logger.info(
            "extracted object",
            tenant_id=parsed.tenant_id,
            namespace=parsed.namespace,
            path=parsed.path,
        )
        processed += 1
    return processed


def handler(event: dict[str, Any], context: object = None) -> dict[str, Any]:
    """Lambda entrypoint."""
    settings = load_settings()
    configure_logging(settings.log_level)
    object_keys = object_keys_from_event(event)
    ingest = IngestService(
        get_catalog_store(settings),
        get_object_store(settings),
        build_pipeline(
            settings.extraction_ladder_names, min_confidence=settings.extraction_min_confidence
        ),
    )
    processed = asyncio.run(process_keys(ingest, object_keys))
    logger.info("batch complete", received=len(object_keys), processed=processed)
    return {"processed": processed}
