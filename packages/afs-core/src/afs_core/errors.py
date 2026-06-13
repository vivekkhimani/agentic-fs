"""The closed error vocabulary and the ``AfsError`` hierarchy.

Every error agentic-fs raises across the wire carries a code from the closed
:class:`ErrorCode` enum and serializes to an RFC 9457 ``application/problem+json``
envelope. The vocabulary is closed on purpose: clients (and the MCP tool layer)
can branch on a small, stable set of codes instead of parsing prose.

Design note — **misses are 404, never 403** (plan §4.1): a caller must not be
able to tell "exists but forbidden" from "does not exist", or they could
enumerate tenants/namespaces/documents. So the not-found errors below all map to
404 and there is intentionally no 403 for resource access.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Closed vocabulary of machine-readable error codes."""

    # Request / validation
    VALIDATION_ERROR = "validation_error"
    INVALID_KEY = "invalid_key"
    INVALID_NAMESPACE = "invalid_namespace"

    # Not found (also used to hide forbidden — see module docstring)
    NOT_FOUND = "not_found"
    TENANT_NOT_FOUND = "tenant_not_found"
    NAMESPACE_NOT_FOUND = "namespace_not_found"
    DOCUMENT_NOT_FOUND = "document_not_found"

    # AuthN / AuthZ
    UNAUTHENTICATED = "unauthenticated"
    INSUFFICIENT_SCOPE = "insufficient_scope"

    # Read-path / capability
    CATALOG_ONLY = "catalog_only"
    SEARCH_NOT_ENABLED = "search_not_enabled"
    BUDGET_EXCEEDED = "budget_exceeded"

    # Write-path / quota
    QUOTA_EXCEEDED = "quota_exceeded"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    CONFLICT = "conflict"

    # Extraction
    EXTRACTION_FAILED = "extraction_failed"

    # Catch-all
    INTERNAL = "internal"


class AfsError(Exception):
    """Base for every agentic-fs error.

    Carries a closed :class:`ErrorCode`, an HTTP status, and an optional
    ``detail`` map; serializes to an RFC 9457 problem object via
    :meth:`to_problem`.
    """

    code: ErrorCode = ErrorCode.INTERNAL
    http_status: int = 500
    title: str = "Internal error"

    def __init__(
        self,
        message: str | None = None,
        *,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.title
        self.detail = detail or {}
        super().__init__(self.message)

    def to_problem(self, *, instance: str | None = None) -> dict[str, Any]:
        """Render as an RFC 9457 ``application/problem+json`` object."""
        problem: dict[str, Any] = {
            "type": f"https://agentic-fs.dev/errors/{self.code.value}",
            "title": self.title,
            "status": self.http_status,
            "code": self.code.value,
            "detail": self.message,
        }
        if instance is not None:
            problem["instance"] = instance
        problem.update(self.detail)
        return problem


# --- 4xx: client ---------------------------------------------------------------


class ValidationError(AfsError):
    code = ErrorCode.VALIDATION_ERROR
    http_status = 400
    title = "Validation error"


class InvalidKeyError(ValidationError):
    code = ErrorCode.INVALID_KEY
    title = "Invalid object key"


class InvalidNamespaceError(ValidationError):
    code = ErrorCode.INVALID_NAMESPACE
    title = "Invalid namespace"


class UnauthenticatedError(AfsError):
    code = ErrorCode.UNAUTHENTICATED
    http_status = 401
    title = "Unauthenticated"


class InsufficientScopeError(AfsError):
    code = ErrorCode.INSUFFICIENT_SCOPE
    http_status = 403
    title = "Insufficient scope"


class NotFoundError(AfsError):
    """Generic 404. Also the disguise for forbidden resource access (§4.1)."""

    code = ErrorCode.NOT_FOUND
    http_status = 404
    title = "Not found"


class TenantNotFoundError(NotFoundError):
    code = ErrorCode.TENANT_NOT_FOUND
    title = "Tenant not found"


class NamespaceNotFoundError(NotFoundError):
    code = ErrorCode.NAMESPACE_NOT_FOUND
    title = "Namespace not found"


class DocumentNotFoundError(NotFoundError):
    code = ErrorCode.DOCUMENT_NOT_FOUND
    title = "Document not found"


class ConflictError(AfsError):
    code = ErrorCode.CONFLICT
    http_status = 409
    title = "Conflict"


class PayloadTooLargeError(AfsError):
    code = ErrorCode.PAYLOAD_TOO_LARGE
    http_status = 413
    title = "Payload too large"


class QuotaExceededError(AfsError):
    code = ErrorCode.QUOTA_EXCEEDED
    http_status = 429
    title = "Quota exceeded"


class BudgetExceededError(AfsError):
    code = ErrorCode.BUDGET_EXCEEDED
    http_status = 422
    title = "Budget exceeded"


class CatalogOnlyError(AfsError):
    """The document exists and is cite-able, but its contents aren't readable yet."""

    code = ErrorCode.CATALOG_ONLY
    http_status = 422
    title = "Document is catalog-only"


class SearchNotEnabledError(AfsError):
    code = ErrorCode.SEARCH_NOT_ENABLED
    http_status = 422
    title = "Search is not enabled"


# --- 5xx: server ---------------------------------------------------------------


class ExtractionFailedError(AfsError):
    code = ErrorCode.EXTRACTION_FAILED
    http_status = 500
    title = "Extraction failed"


__all__ = [
    "AfsError",
    "BudgetExceededError",
    "CatalogOnlyError",
    "ConflictError",
    "DocumentNotFoundError",
    "ErrorCode",
    "ExtractionFailedError",
    "InsufficientScopeError",
    "InvalidKeyError",
    "InvalidNamespaceError",
    "NamespaceNotFoundError",
    "NotFoundError",
    "PayloadTooLargeError",
    "QuotaExceededError",
    "SearchNotEnabledError",
    "TenantNotFoundError",
    "UnauthenticatedError",
    "ValidationError",
]
