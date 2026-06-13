"""Control-plane records: tenants, namespaces, principals, scratch usage (plan §5.1, §6)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TenantRecord(BaseModel):
    tenant_id: str
    display_name: str | None = None
    created_at: datetime
    updated_at: datetime


class NamespaceRecord(BaseModel):
    """A namespace is runtime data, validated at admission time (plan §3.2).

    ``entity_segment`` declares whether the first path segment is an entity id
    (which powers prefix narrowing); ``capabilities`` gates which tools are
    visible/callable for the namespace.
    """

    tenant_id: str
    name: str
    description: str | None = None
    entity_segment: bool = False
    capabilities: frozenset[str] = Field(default_factory=frozenset)
    created_at: datetime
    updated_at: datetime


class PrincipalRecord(BaseModel):
    """An API client: its OAuth scopes, namespace grants, and scratch limits."""

    tenant_id: str
    principal_id: str
    scopes: frozenset[str] = Field(default_factory=frozenset)
    namespace_grants: frozenset[str] = Field(default_factory=frozenset)
    scratch_quota_bytes: int | None = None
    scratch_ttl_days: int | None = None
    created_at: datetime
    updated_at: datetime


class ScratchUsage(BaseModel):
    """A principal's current scratch consumption against its quota."""

    tenant_id: str
    principal_id: str
    bytes_used: int = 0
    objects_used: int = 0
    quota_bytes: int | None = None


class SyncCheckpoint(BaseModel):
    """A connector's persisted sync cursor (checkpoints live server-side)."""

    connector_id: str
    cursor: str | None = None
    updated_at: datetime | None = None
