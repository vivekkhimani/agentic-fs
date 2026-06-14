"""configure_logging wires structlog + the stdlib bridge so app logs surface."""

from __future__ import annotations

import json
import logging

import structlog

from afs_server.logging_config import configure_logging


def test_sets_afs_logger_level_keeps_root_quiet() -> None:
    configure_logging("DEBUG")
    assert logging.getLogger("afs_server").level == logging.DEBUG
    # Root stays at WARNING so boto3/uvicorn don't flood CloudWatch.
    assert logging.getLogger().level == logging.WARNING


def test_unknown_level_falls_back_to_info() -> None:
    configure_logging("not-a-level")
    assert logging.getLogger("afs_server").level == logging.INFO


def test_idempotent_single_root_handler() -> None:
    configure_logging("INFO")
    configure_logging("INFO")
    configure_logging("INFO")
    assert len(logging.getLogger().handlers) == 1


def test_structlog_event_renders_json_with_fields(capsys) -> None:
    # Not a TTY under pytest → JSON renderer (the CloudWatch path).
    configure_logging("INFO")
    structlog.get_logger("afs_server.test").info("extracted object", pages=2, extractor="pdf")
    line = capsys.readouterr().err.strip().splitlines()[-1]
    record = json.loads(line)  # must be valid JSON
    assert record["event"] == "extracted object"
    assert record["pages"] == 2
    assert record["extractor"] == "pdf"
    assert record["level"] == "info"


def test_stdlib_logger_bridges_through_structlog(capsys) -> None:
    # An existing logging.getLogger call site (e.g. the extraction pipeline) must
    # still render through the same JSON formatter.
    configure_logging("INFO")
    logging.getLogger("afs_server.extraction").info("normalizer declined")
    line = capsys.readouterr().err.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["event"] == "normalizer declined"
    assert record["logger"] == "afs_server.extraction"
