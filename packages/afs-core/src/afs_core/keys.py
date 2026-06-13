"""The single definition of the S3 key scheme (plan §3.2).

Nothing else in agentic-fs concatenates an object key — every consumer builds,
parses, and validates through here. The scheme is **channel-first** so that one
EventBridge rule (``prefix: tenants/``) feeds extraction, Bedrock KB syncs from a
prefix containing only embeddable text, and lifecycle rules are plain prefix
rules (plan §3.1):

    tenants/{tenant}/{namespace}/{relpath}                  raw canonical documents
    scratch/{tenant}/{principal}/{relpath}                  agent scratch (TTL'd)
    derived/text/{tenant}/{ns}/{doc_id}/{page:04d}.md       extracted text layer
    derived/text/{tenant}/{ns}/{doc_id}/{page:04d}.md.metadata.json   KB sidecar
    derived/meta/{tenant}/{ns}/{doc_id}/manifest.json       extraction manifest
    derived/tree/{tenant}/{ns}.json.zst                     path-tree artifact

``parse_key`` returns ``None`` for anything nonconforming — it never guesses.
``is_indexable`` is the one predicate every consumer (cataloger, extractor,
index-sync, tree builder, search scope) uses to exclude ``scratch/`` and
``derived/``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from afs_core.errors import InvalidKeyError

PAGE_DIGITS = 4
MAX_PAGE = 10**PAGE_DIGITS - 1

# Lowercase slugs for tenant / namespace / principal ids.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
# doc_id is a ULID (uppercase Crockford base32) or similar opaque id.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# Segments a relpath may never contain (traversal + channel words + dotfiles).
_RESERVED_SEGMENTS = frozenset({"", ".", "..", "tenants", "scratch", "derived"})

_TREE_SUFFIX = ".json.zst"
_TEXT_SUFFIX = ".md"
_METADATA_SUFFIX = ".metadata.json"
_MANIFEST_NAME = "manifest.json"


class Channel(StrEnum):
    """Top-level key channels."""

    ORIGINAL = "original"  # tenants/
    SCRATCH = "scratch"  # scratch/
    DERIVED_TEXT = "derived_text"  # derived/text/
    DERIVED_META = "derived_meta"  # derived/meta/
    DERIVED_TREE = "derived_tree"  # derived/tree/


@dataclass(frozen=True, slots=True)
class ParsedKey:
    """The structured decomposition of a conforming key.

    Fields not relevant to a channel stay ``None`` (e.g. an ORIGINAL key has no
    ``doc_id``; a DERIVED_TREE key has no ``path``).
    """

    channel: Channel
    tenant_id: str
    namespace: str | None = None
    path: str | None = None
    principal_id: str | None = None
    doc_id: str | None = None
    page: int | None = None
    is_metadata: bool = False


# --- validation helpers --------------------------------------------------------


def _is_slug(value: str) -> bool:
    return bool(_SLUG_RE.fullmatch(value))


def _is_id(value: str) -> bool:
    return bool(_ID_RE.fullmatch(value))


def _relpath_ok(relpath: str) -> bool:
    if not relpath or relpath.startswith("/"):
        return False
    return all(
        seg not in _RESERVED_SEGMENTS and not seg.startswith("_") for seg in relpath.split("/")
    )


def validate_slug(value: str, *, field: str) -> str:
    if not _is_slug(value):
        raise InvalidKeyError(
            f"{field} must be a lowercase slug", detail={"field": field, "value": value}
        )
    return value


def validate_id(value: str, *, field: str) -> str:
    if not _is_id(value):
        raise InvalidKeyError(
            f"{field} must be alphanumeric", detail={"field": field, "value": value}
        )
    return value


def validate_relpath(relpath: str) -> str:
    """Reject traversal, absolute paths, reserved/dotfile segments. One code path."""
    if not _relpath_ok(relpath):
        raise InvalidKeyError("invalid relpath", detail={"relpath": relpath})
    return relpath


def _validate_page(page: int) -> int:
    if not (0 <= page <= MAX_PAGE):
        raise InvalidKeyError(f"page must be in [0, {MAX_PAGE}]", detail={"page": page})
    return page


# --- builders ------------------------------------------------------------------


def originals_key(tenant_id: str, namespace: str, path: str) -> str:
    validate_slug(tenant_id, field="tenant_id")
    validate_slug(namespace, field="namespace")
    validate_relpath(path)
    return f"tenants/{tenant_id}/{namespace}/{path}"


def scratch_key(tenant_id: str, principal_id: str, path: str) -> str:
    validate_slug(tenant_id, field="tenant_id")
    validate_slug(principal_id, field="principal_id")
    validate_relpath(path)
    return f"scratch/{tenant_id}/{principal_id}/{path}"


def derived_text_key(tenant_id: str, namespace: str, doc_id: str, page: int) -> str:
    validate_slug(tenant_id, field="tenant_id")
    validate_slug(namespace, field="namespace")
    validate_id(doc_id, field="doc_id")
    _validate_page(page)
    return f"derived/text/{tenant_id}/{namespace}/{doc_id}/{page:0{PAGE_DIGITS}d}{_TEXT_SUFFIX}"


def derived_text_metadata_key(tenant_id: str, namespace: str, doc_id: str, page: int) -> str:
    return derived_text_key(tenant_id, namespace, doc_id, page) + _METADATA_SUFFIX


def derived_meta_key(tenant_id: str, namespace: str, doc_id: str) -> str:
    validate_slug(tenant_id, field="tenant_id")
    validate_slug(namespace, field="namespace")
    validate_id(doc_id, field="doc_id")
    return f"derived/meta/{tenant_id}/{namespace}/{doc_id}/{_MANIFEST_NAME}"


def tree_key(tenant_id: str, namespace: str) -> str:
    validate_slug(tenant_id, field="tenant_id")
    validate_slug(namespace, field="namespace")
    return f"derived/tree/{tenant_id}/{namespace}{_TREE_SUFFIX}"


# --- parsing -------------------------------------------------------------------


def parse_key(key: str) -> ParsedKey | None:
    """Decompose a key, or return ``None`` if it doesn't conform. Never guesses."""
    if key.startswith("derived/tree/"):
        return _parse_tree(key.removeprefix("derived/tree/"))
    if key.startswith("derived/text/"):
        return _parse_text(key.removeprefix("derived/text/"))
    if key.startswith("derived/meta/"):
        return _parse_meta(key.removeprefix("derived/meta/"))
    if key.startswith("scratch/"):
        return _parse_scratch(key.removeprefix("scratch/"))
    if key.startswith("tenants/"):
        return _parse_original(key.removeprefix("tenants/"))
    return None


def _parse_tree(rest: str) -> ParsedKey | None:
    segs = rest.split("/")
    if len(segs) != 2 or not segs[1].endswith(_TREE_SUFFIX):
        return None
    tenant, ns = segs[0], segs[1].removesuffix(_TREE_SUFFIX)
    if not (_is_slug(tenant) and _is_slug(ns)):
        return None
    return ParsedKey(Channel.DERIVED_TREE, tenant_id=tenant, namespace=ns)


def _parse_text(rest: str) -> ParsedKey | None:
    segs = rest.split("/")
    if len(segs) != 4:
        return None
    tenant, ns, doc_id, filename = segs
    is_metadata = filename.endswith(_METADATA_SUFFIX)
    base = filename.removesuffix(_METADATA_SUFFIX) if is_metadata else filename
    if not base.endswith(_TEXT_SUFFIX):
        return None
    page_str = base.removesuffix(_TEXT_SUFFIX)
    if not (page_str.isdigit() and len(page_str) == PAGE_DIGITS):
        return None
    if not (_is_slug(tenant) and _is_slug(ns) and _is_id(doc_id)):
        return None
    return ParsedKey(
        Channel.DERIVED_TEXT,
        tenant_id=tenant,
        namespace=ns,
        doc_id=doc_id,
        page=int(page_str),
        is_metadata=is_metadata,
    )


def _parse_meta(rest: str) -> ParsedKey | None:
    segs = rest.split("/")
    if len(segs) != 4 or segs[3] != _MANIFEST_NAME:
        return None
    tenant, ns, doc_id, _ = segs
    if not (_is_slug(tenant) and _is_slug(ns) and _is_id(doc_id)):
        return None
    return ParsedKey(Channel.DERIVED_META, tenant_id=tenant, namespace=ns, doc_id=doc_id)


def _parse_scratch(rest: str) -> ParsedKey | None:
    segs = rest.split("/")
    if len(segs) < 3:
        return None
    tenant, principal, relpath = segs[0], segs[1], "/".join(segs[2:])
    if not (_is_slug(tenant) and _is_slug(principal) and _relpath_ok(relpath)):
        return None
    return ParsedKey(Channel.SCRATCH, tenant_id=tenant, principal_id=principal, path=relpath)


def _parse_original(rest: str) -> ParsedKey | None:
    segs = rest.split("/")
    if len(segs) < 3:
        return None
    tenant, ns, relpath = segs[0], segs[1], "/".join(segs[2:])
    if not (_is_slug(tenant) and _is_slug(ns) and _relpath_ok(relpath)):
        return None
    return ParsedKey(Channel.ORIGINAL, tenant_id=tenant, namespace=ns, path=relpath)


def is_indexable(key: str) -> bool:
    """True only for raw canonical documents under ``tenants/`` (plan §3.2).

    The single predicate that excludes ``scratch/`` and ``derived/`` from the
    cataloger, extractor, index-sync, tree builder, and search scope.
    """
    parsed = parse_key(key)
    return parsed is not None and parsed.channel is Channel.ORIGINAL


__all__ = [
    "Channel",
    "ParsedKey",
    "derived_meta_key",
    "derived_text_key",
    "derived_text_metadata_key",
    "is_indexable",
    "originals_key",
    "parse_key",
    "scratch_key",
    "tree_key",
    "validate_id",
    "validate_relpath",
    "validate_slug",
]
