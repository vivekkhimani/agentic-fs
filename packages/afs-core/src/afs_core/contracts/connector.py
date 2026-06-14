"""The ``Connector`` contract (plan §8) — the source seam.

A connector is the source-specific half of ingestion: it discovers documents at
an external source and fetches their bytes. Everything source-agnostic — change
detection, batching, retries, calling the ingest API, pruning — lives in the
sync engine (``afs_connector_sdk``), so a connector author writes only two small
methods and never learns the rest of the system.

The contract is intentionally **synchronous**: most source SDKs (boto3, the
Google API client, filesystem calls) are sync, and the engine provides
concurrency by running ``fetch`` in a thread pool. Add your own: implement this
Protocol, certify it against ``afs_core.testing.ConnectorConformance``, and
register it under the ``afs.connectors`` entry-point group.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from afs_core.models import SourceItem


@runtime_checkable
class Connector(Protocol):
    name: str

    def discover(self) -> Iterable[SourceItem]:
        """Enumerate the documents available at the source."""
        ...

    def fetch(self, item: SourceItem) -> bytes:
        """Return the raw bytes for one discovered item."""
        ...
