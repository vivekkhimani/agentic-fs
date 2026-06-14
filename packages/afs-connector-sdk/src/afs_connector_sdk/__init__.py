"""agentic-fs connector SDK — crawl a source and ingest into agentic-fs.

Public surface: the ``IngestClient`` (HTTP), the ``SyncEngine`` (discover → skip
unchanged → ingest → prune), request signers, and ``build_connector``. The
``fs-crawler`` CLI wires them together. Source-specific logic is a
`afs_core.contracts.Connector`; this package ships Local FS and S3.
"""

from afs_connector_sdk.auth import NoAuth, RequestSigner, SigV4Signer
from afs_connector_sdk.client import IngestClient
from afs_connector_sdk.engine import SyncEngine, SyncReport
from afs_connector_sdk.registry import build_connector

__all__ = [
    "IngestClient",
    "NoAuth",
    "RequestSigner",
    "SigV4Signer",
    "SyncEngine",
    "SyncReport",
    "build_connector",
]
