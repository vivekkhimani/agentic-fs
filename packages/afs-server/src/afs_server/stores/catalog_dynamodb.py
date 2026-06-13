"""DynamoDB implementation of the ``CatalogStore`` contract (plan §5.1).

Single-table design over the table the ``catalog_dynamodb`` Terraform module
provisions: ``PK``/``SK`` + three GSIs (``gsi1_by_doc``, ``gsi2_by_checksum``,
sparse ``gsi3_by_extraction_status``) + TTL on ``expires_at``.

Logical → physical key mapping (the value schemes live here, not in keys.py
which owns *S3* keys):

    Document         PK=T#{tenant}#NS#{ns}            SK=P#{path}
    Tenant           PK=REGISTRY                      SK=T#{tenant}
    Namespace        PK=T#{tenant}                    SK=NS#{name}
    Principal        PK=T#{tenant}                    SK=PR#{principal}
    Checkpoint       PK=T#{tenant}                    SK=CP#{connector}
    Scratch usage    PK=T#{tenant}#NS#scratch         SK=U#{principal}
    Tree version     PK=T#{tenant}#NS#{ns}            SK=#TREEVER

The full entry/record is stored as JSON in ``doc_json``; queryable fields and GSI
keys are duplicated as top-level attributes. Sync boto3 + asyncio.to_thread
(ADR 0001).
"""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from afs_core.errors import NotFoundError, QuotaExceededError
from afs_core.models import (
    CatalogEntry,
    ExtractionState,
    NamespaceRecord,
    Page,
    PrincipalRecord,
    ScratchUsage,
    SyncCheckpoint,
    TenantRecord,
)

if TYPE_CHECKING:
    from afs_server.settings import Settings

# Statuses kept in the sparse status GSI (everything except terminal "extracted").
_SPARSE_STATUSES = {"pending", "extracting", "catalog_only"}


def _encode_cursor(key: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def _decode_cursor(cursor: str) -> dict[str, Any]:
    return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())


class DynamoDBCatalogStore:
    """``CatalogStore`` backed by a single DynamoDB table."""

    def __init__(
        self, *, table_name: str, region: str = "us-east-1", endpoint_url: str | None = None
    ) -> None:
        self._table_name = table_name
        self._region = region
        self._endpoint_url = endpoint_url
        self._table_cache: Any = None

    @property
    def _table(self) -> Any:
        if self._table_cache is None:
            resource = boto3.resource(
                "dynamodb", region_name=self._region, endpoint_url=self._endpoint_url
            )
            self._table_cache = resource.Table(self._table_name)
        return self._table_cache

    @classmethod
    def from_settings(cls, settings: Settings) -> DynamoDBCatalogStore:
        return cls(
            table_name=settings.catalog_table,
            region=settings.region,
            endpoint_url=settings.dynamodb_endpoint_url,
        )

    # --- key helpers ---
    @staticmethod
    def _doc_pk(tenant_id: str, namespace: str) -> str:
        return f"T#{tenant_id}#NS#{namespace}"

    @staticmethod
    def _tenant_pk(tenant_id: str) -> str:
        return f"T#{tenant_id}"

    @staticmethod
    def _scratch_pk(tenant_id: str) -> str:
        return f"T#{tenant_id}#NS#scratch"

    def _entry_item(self, entry: CatalogEntry) -> dict[str, Any]:
        item: dict[str, Any] = {
            "PK": self._doc_pk(entry.tenant_id, entry.namespace),
            "SK": f"P#{entry.path}",
            "GSI1PK": f"T#{entry.tenant_id}#DOC#{entry.entry_id}",
            "path": entry.path,
            "status": entry.extraction.status,
            "checksum": entry.checksum,
            "deleted": entry.deleted_at is not None,
            "doc_json": entry.model_dump_json(),
        }
        if entry.deleted_at is None:
            item["GSI2PK"] = f"T#{entry.tenant_id}#SHA#{entry.checksum}"
            if entry.extraction.status in _SPARSE_STATUSES:
                item["GSI3PK"] = f"STATUS#{entry.extraction.status}"
                item["GSI3SK"] = f"{entry.tenant_id}#{entry.namespace}#{entry.path}"
        return item

    @staticmethod
    def _entry_from_item(item: dict[str, Any]) -> CatalogEntry:
        return CatalogEntry.model_validate_json(item["doc_json"])

    # --- tree version (atomic counter, bumped on every write) ---
    async def _bump_tree(self, tenant_id: str, namespace: str) -> None:
        def _bump() -> None:
            self._table.update_item(
                Key={"PK": self._doc_pk(tenant_id, namespace), "SK": "#TREEVER"},
                UpdateExpression="ADD #v :one",
                ExpressionAttributeNames={"#v": "version"},
                ExpressionAttributeValues={":one": 1},
            )

        await _to_thread(_bump)

    async def tree_version(self, tenant_id: str, namespace: str) -> str:
        def _read() -> str:
            resp = self._table.get_item(
                Key={"PK": self._doc_pk(tenant_id, namespace), "SK": "#TREEVER"}
            )
            return str(resp.get("Item", {}).get("version", 0))

        return await _to_thread(_read)

    # --- entries ---
    async def put_entry(self, entry: CatalogEntry) -> None:
        await _to_thread(self._table.put_item, Item=self._entry_item(entry))
        await self._bump_tree(entry.tenant_id, entry.namespace)

    async def get_entry(self, tenant_id: str, namespace: str, path: str) -> CatalogEntry | None:
        def _get() -> CatalogEntry | None:
            resp = self._table.get_item(
                Key={"PK": self._doc_pk(tenant_id, namespace), "SK": f"P#{path}"}
            )
            item = resp.get("Item")
            if item is None or item.get("deleted"):
                return None
            return self._entry_from_item(item)

        return await _to_thread(_get)

    async def delete_entry(
        self, tenant_id: str, namespace: str, path: str, *, hard: bool = False
    ) -> None:
        key = {"PK": self._doc_pk(tenant_id, namespace), "SK": f"P#{path}"}
        if hard:
            await _to_thread(self._table.delete_item, Key=key)
            await self._bump_tree(tenant_id, namespace)
            return

        existing = await self._get_raw(tenant_id, namespace, path)
        if existing is None:
            return
        entry = self._entry_from_item(existing)
        tombstoned = entry.model_copy(update={"deleted_at": datetime.now(UTC)})
        await _to_thread(self._table.put_item, Item=self._entry_item(tombstoned))
        await self._bump_tree(tenant_id, namespace)

    async def _get_raw(self, tenant_id: str, namespace: str, path: str) -> dict[str, Any] | None:
        def _get() -> dict[str, Any] | None:
            resp = self._table.get_item(
                Key={"PK": self._doc_pk(tenant_id, namespace), "SK": f"P#{path}"}
            )
            return resp.get("Item")

        return await _to_thread(_get)

    async def list_entries(
        self,
        tenant_id: str,
        namespace: str,
        *,
        prefix: str = "",
        include_deleted: bool = False,
        cursor: str | None = None,
        limit: int = 1000,
    ) -> Page[CatalogEntry]:
        def _list() -> Page[CatalogEntry]:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": Key("PK").eq(self._doc_pk(tenant_id, namespace))
                & Key("SK").begins_with(f"P#{prefix}"),
                "Limit": limit,
            }
            if not include_deleted:
                kwargs["FilterExpression"] = Attr("deleted").eq(False)
            if cursor:
                kwargs["ExclusiveStartKey"] = _decode_cursor(cursor)
            resp = self._table.query(**kwargs)
            items = [self._entry_from_item(i) for i in resp.get("Items", [])]
            last = resp.get("LastEvaluatedKey")
            return Page(items=items, next_cursor=_encode_cursor(last) if last else None)

        return await _to_thread(_list)

    async def find_by_checksum(self, tenant_id: str, checksum: str) -> list[CatalogEntry]:
        def _find() -> list[CatalogEntry]:
            resp = self._table.query(
                IndexName="gsi2_by_checksum",
                KeyConditionExpression=Key("GSI2PK").eq(f"T#{tenant_id}#SHA#{checksum}"),
            )
            return [self._entry_from_item(i) for i in resp.get("Items", [])]

        return await _to_thread(_find)

    async def set_extraction(
        self, tenant_id: str, namespace: str, path: str, state: ExtractionState
    ) -> None:
        existing = await self._get_raw(tenant_id, namespace, path)
        if existing is None:
            raise NotFoundError("entry not found", detail={"path": path})
        entry = self._entry_from_item(existing).model_copy(
            update={"extraction": state, "updated_at": datetime.now(UTC)}
        )
        await _to_thread(self._table.put_item, Item=self._entry_item(entry))
        await self._bump_tree(tenant_id, namespace)

    async def list_by_extraction_status(
        self, status: str, *, cursor: str | None = None, limit: int = 100
    ) -> Page[CatalogEntry]:
        def _list() -> Page[CatalogEntry]:
            kwargs: dict[str, Any] = {
                "IndexName": "gsi3_by_extraction_status",
                "KeyConditionExpression": Key("GSI3PK").eq(f"STATUS#{status}"),
                "Limit": limit,
            }
            if cursor:
                kwargs["ExclusiveStartKey"] = _decode_cursor(cursor)
            resp = self._table.query(**kwargs)
            items = [self._entry_from_item(i) for i in resp.get("Items", [])]
            last = resp.get("LastEvaluatedKey")
            return Page(items=items, next_cursor=_encode_cursor(last) if last else None)

        return await _to_thread(_list)

    # --- control records ---
    async def put_tenant(self, tenant: TenantRecord) -> None:
        await _to_thread(
            self._table.put_item,
            Item={
                "PK": "REGISTRY",
                "SK": f"T#{tenant.tenant_id}",
                "doc_json": tenant.model_dump_json(),
            },
        )

    async def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        def _get() -> TenantRecord | None:
            resp = self._table.get_item(Key={"PK": "REGISTRY", "SK": f"T#{tenant_id}"})
            item = resp.get("Item")
            return TenantRecord.model_validate_json(item["doc_json"]) if item else None

        return await _to_thread(_get)

    async def list_tenants(
        self, *, cursor: str | None = None, limit: int = 100
    ) -> Page[TenantRecord]:
        def _list() -> Page[TenantRecord]:
            kwargs: dict[str, Any] = {
                "KeyConditionExpression": Key("PK").eq("REGISTRY"),
                "Limit": limit,
            }
            if cursor:
                kwargs["ExclusiveStartKey"] = _decode_cursor(cursor)
            resp = self._table.query(**kwargs)
            items = [TenantRecord.model_validate_json(i["doc_json"]) for i in resp.get("Items", [])]
            last = resp.get("LastEvaluatedKey")
            return Page(items=items, next_cursor=_encode_cursor(last) if last else None)

        return await _to_thread(_list)

    async def put_namespace(self, ns: NamespaceRecord) -> None:
        await _to_thread(
            self._table.put_item,
            Item={
                "PK": self._tenant_pk(ns.tenant_id),
                "SK": f"NS#{ns.name}",
                "doc_json": ns.model_dump_json(),
            },
        )

    async def get_namespace(self, tenant_id: str, name: str) -> NamespaceRecord | None:
        def _get() -> NamespaceRecord | None:
            resp = self._table.get_item(Key={"PK": self._tenant_pk(tenant_id), "SK": f"NS#{name}"})
            item = resp.get("Item")
            return NamespaceRecord.model_validate_json(item["doc_json"]) if item else None

        return await _to_thread(_get)

    async def list_namespaces(self, tenant_id: str) -> list[NamespaceRecord]:
        def _list() -> list[NamespaceRecord]:
            resp = self._table.query(
                KeyConditionExpression=Key("PK").eq(self._tenant_pk(tenant_id))
                & Key("SK").begins_with("NS#")
            )
            return [
                NamespaceRecord.model_validate_json(i["doc_json"]) for i in resp.get("Items", [])
            ]

        return await _to_thread(_list)

    async def delete_namespace(self, tenant_id: str, name: str) -> None:
        await _to_thread(
            self._table.delete_item, Key={"PK": self._tenant_pk(tenant_id), "SK": f"NS#{name}"}
        )

    async def put_principal(self, p: PrincipalRecord) -> None:
        await _to_thread(
            self._table.put_item,
            Item={
                "PK": self._tenant_pk(p.tenant_id),
                "SK": f"PR#{p.principal_id}",
                "doc_json": p.model_dump_json(),
            },
        )

    async def get_principal(self, tenant_id: str, principal_id: str) -> PrincipalRecord | None:
        def _get() -> PrincipalRecord | None:
            resp = self._table.get_item(
                Key={"PK": self._tenant_pk(tenant_id), "SK": f"PR#{principal_id}"}
            )
            item = resp.get("Item")
            return PrincipalRecord.model_validate_json(item["doc_json"]) if item else None

        return await _to_thread(_get)

    async def list_principals(self, tenant_id: str) -> list[PrincipalRecord]:
        def _list() -> list[PrincipalRecord]:
            resp = self._table.query(
                KeyConditionExpression=Key("PK").eq(self._tenant_pk(tenant_id))
                & Key("SK").begins_with("PR#")
            )
            return [
                PrincipalRecord.model_validate_json(i["doc_json"]) for i in resp.get("Items", [])
            ]

        return await _to_thread(_list)

    # --- checkpoints ---
    async def get_checkpoint(self, tenant_id: str, connector_id: str) -> SyncCheckpoint | None:
        def _get() -> SyncCheckpoint | None:
            resp = self._table.get_item(
                Key={"PK": self._tenant_pk(tenant_id), "SK": f"CP#{connector_id}"}
            )
            item = resp.get("Item")
            return SyncCheckpoint.model_validate_json(item["doc_json"]) if item else None

        return await _to_thread(_get)

    async def put_checkpoint(self, tenant_id: str, connector_id: str, cp: SyncCheckpoint) -> None:
        await _to_thread(
            self._table.put_item,
            Item={
                "PK": self._tenant_pk(tenant_id),
                "SK": f"CP#{connector_id}",
                "doc_json": cp.model_dump_json(),
            },
        )

    # --- scratch quota (atomic via conditional update) ---
    async def get_scratch_usage(self, tenant_id: str, principal_id: str) -> ScratchUsage:
        def _get() -> ScratchUsage:
            resp = self._table.get_item(
                Key={"PK": self._scratch_pk(tenant_id), "SK": f"U#{principal_id}"}
            )
            item = resp.get("Item") or {}
            return ScratchUsage(
                tenant_id=tenant_id,
                principal_id=principal_id,
                bytes_used=int(item.get("bytes_used", 0)),
                objects_used=int(item.get("objects_used", 0)),
            )

        return await _to_thread(_get)

    async def adjust_scratch_usage(
        self, tenant_id: str, principal_id: str, *, delta_bytes: int, delta_objects: int
    ) -> ScratchUsage:
        principal = await self.get_principal(tenant_id, principal_id)
        quota = principal.scratch_quota_bytes if principal else None

        def _adjust() -> ScratchUsage:
            kwargs: dict[str, Any] = {
                "Key": {"PK": self._scratch_pk(tenant_id), "SK": f"U#{principal_id}"},
                "UpdateExpression": "ADD #b :db, #o :do",
                "ExpressionAttributeNames": {"#b": "bytes_used", "#o": "objects_used"},
                "ExpressionAttributeValues": {":db": delta_bytes, ":do": delta_objects},
                "ReturnValues": "ALL_NEW",
            }
            if quota is not None and delta_bytes > 0:
                kwargs["ConditionExpression"] = "attribute_not_exists(#b) OR #b <= :threshold"
                kwargs["ExpressionAttributeValues"][":threshold"] = quota - delta_bytes
            try:
                resp = self._table.update_item(**kwargs)
            except ClientError as err:
                if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                    raise QuotaExceededError(
                        "scratch quota exceeded", detail={"quota_bytes": quota}
                    ) from err
                raise
            item = resp["Attributes"]
            return ScratchUsage(
                tenant_id=tenant_id,
                principal_id=principal_id,
                bytes_used=int(item.get("bytes_used", 0)),
                objects_used=int(item.get("objects_used", 0)),
                quota_bytes=quota,
            )

        return await _to_thread(_adjust)


async def _to_thread(fn: Any, *args: Any, **kwargs: Any) -> Any:
    return await asyncio.to_thread(fn, *args, **kwargs)
