"""Core DTOs and control records (pydantic v2)."""

from afs_core.models.connector import SourceItem
from afs_core.models.control import (
    NamespaceRecord,
    PrincipalRecord,
    ScratchUsage,
    SyncCheckpoint,
    TenantRecord,
)
from afs_core.models.core import (
    CatalogEntry,
    ExtractionState,
    Page,
    SourceRef,
)
from afs_core.models.extraction import (
    NormalizedDocument,
    PageText,
    QualityReport,
    SourceDocument,
)
from afs_core.models.objects import (
    ObjectStat,
    PresignedPut,
)

__all__ = [
    "CatalogEntry",
    "ExtractionState",
    "NamespaceRecord",
    "NormalizedDocument",
    "ObjectStat",
    "Page",
    "PageText",
    "PresignedPut",
    "PrincipalRecord",
    "QualityReport",
    "ScratchUsage",
    "SourceDocument",
    "SourceItem",
    "SourceRef",
    "SyncCheckpoint",
    "TenantRecord",
]
