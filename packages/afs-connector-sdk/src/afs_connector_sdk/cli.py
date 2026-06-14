"""``fs-crawler`` — crawl a source and ingest its documents into agentic-fs (Click)."""

from __future__ import annotations

import asyncio
import sys

import click

from afs_connector_sdk.client import IngestClient
from afs_connector_sdk.engine import SyncEngine, SyncReport
from afs_connector_sdk.registry import build_connector


def _parse_options(pairs: tuple[str, ...]) -> dict[str, str]:
    options: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise click.BadParameter(f"--opt expects KEY=VALUE, got {pair!r}")
        key, value = pair.split("=", 1)
        options[key] = value
    return options


@click.command()
@click.option("--connector", default="local", help="Connector name (local, s3, or a plugin).")
@click.option(
    "--source", required=True, help="Connector source (a directory, or s3://bucket/prefix)."
)
@click.option("--api-url", required=True, help="agentic-fs API base URL.")
@click.option("--namespace", required=True, help="Target namespace.")
@click.option(
    "--auth",
    type=click.Choice(["none", "sigv4"]),
    default="none",
    help="How to authenticate to the API.",
)
@click.option("--region", default="us-east-1", help="AWS region (for --auth sigv4).")
@click.option("--concurrency", type=int, default=8, help="Max documents in flight.")
@click.option("--prune", is_flag=True, help="Delete agentic-fs docs no longer at the source.")
@click.option("--dry-run", is_flag=True, help="Report what would change without writing.")
@click.option(
    "--opt",
    "opts",
    multiple=True,
    metavar="KEY=VALUE",
    help="Connector-specific option (repeatable).",
)
def main(
    connector: str,
    source: str,
    api_url: str,
    namespace: str,
    auth: str,
    region: str,
    concurrency: int,
    prune: bool,
    dry_run: bool,
    opts: tuple[str, ...],
) -> None:
    """Crawl a source and ingest its documents into agentic-fs."""
    try:
        conn = build_connector(connector, source, **_parse_options(opts))
    except (ValueError, RuntimeError) as err:
        raise click.ClickException(str(err)) from err

    signer = None
    if auth == "sigv4":
        from afs_connector_sdk.auth import SigV4Signer

        try:
            signer = SigV4Signer(region=region)
        except RuntimeError as err:
            raise click.ClickException(str(err)) from err

    report = asyncio.run(
        _run(
            conn, api_url, namespace, signer, concurrency=concurrency, prune=prune, dry_run=dry_run
        )
    )
    tag = " (dry-run)" if dry_run else ""
    click.echo(
        f"{connector} -> {namespace}{tag}: "
        f"ingested={report.ingested} skipped={report.skipped} "
        f"deleted={report.deleted} failed={report.failed}"
    )
    for line in report.errors[:20]:
        click.echo(f"  ! {line}", err=True)
    if report.failed:
        sys.exit(1)


async def _run(
    connector: object,
    api_url: str,
    namespace: str,
    signer: object,
    *,
    concurrency: int,
    prune: bool,
    dry_run: bool,
) -> SyncReport:
    async with IngestClient(api_url, signer=signer) as client:  # type: ignore[arg-type]
        engine = SyncEngine(client, concurrency=concurrency, prune=prune, dry_run=dry_run)
        return await engine.sync(connector, namespace)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
