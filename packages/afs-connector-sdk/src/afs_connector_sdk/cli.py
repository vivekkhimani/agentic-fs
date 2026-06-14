"""``fs-crawler`` — crawl a source and ingest its documents into agentic-fs."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from afs_connector_sdk.client import IngestClient
from afs_connector_sdk.engine import SyncEngine, SyncReport
from afs_connector_sdk.registry import build_connector


def _parse_options(pairs: list[str]) -> dict[str, str]:
    options: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--opt expects KEY=VALUE, got {pair!r}")
        key, value = pair.split("=", 1)
        options[key] = value
    return options


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fs-crawler",
        description="Crawl a source and ingest its documents into agentic-fs.",
    )
    add = parser.add_argument
    add("--connector", default="local", help="connector name (local, s3, or a plugin)")
    add("--source", required=True, help="connector source (a directory, or s3://bucket/prefix)")
    add("--api-url", required=True, help="agentic-fs API base URL")
    add("--namespace", required=True, help="target namespace")
    add("--auth", choices=["none", "sigv4"], default="none", help="how to authenticate to the API")
    add("--region", default="us-east-1", help="AWS region (for --auth sigv4)")
    add("--concurrency", type=int, default=8, help="max documents in flight")
    add("--prune", action="store_true", help="delete agentic-fs docs no longer at the source")
    add("--dry-run", action="store_true", help="report what would change without writing")
    parser.add_argument(
        "--opt",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="connector-specific option (repeatable)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        connector = build_connector(args.connector, args.source, **_parse_options(args.opt))
    except (ValueError, RuntimeError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    signer = None
    if args.auth == "sigv4":
        from afs_connector_sdk.auth import SigV4Signer

        try:
            signer = SigV4Signer(region=args.region)
        except RuntimeError as err:
            print(f"error: {err}", file=sys.stderr)
            return 2

    report = asyncio.run(_run(connector, args, signer))
    tag = " (dry-run)" if args.dry_run else ""
    print(
        f"{args.connector} -> {args.namespace}{tag}: "
        f"ingested={report.ingested} skipped={report.skipped} "
        f"deleted={report.deleted} failed={report.failed}"
    )
    for line in report.errors[:20]:
        print(f"  ! {line}", file=sys.stderr)
    return 1 if report.failed else 0


async def _run(connector: object, args: argparse.Namespace, signer: object) -> SyncReport:
    async with IngestClient(args.api_url, signer=signer) as client:  # type: ignore[arg-type]
        engine = SyncEngine(
            client, concurrency=args.concurrency, prune=args.prune, dry_run=args.dry_run
        )
        return await engine.sync(connector, args.namespace)  # type: ignore[arg-type]


if __name__ == "__main__":
    raise SystemExit(main())
