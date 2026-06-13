"""Tests for the closed error vocabulary and the RFC 9457 envelope."""

from __future__ import annotations

from afs_core import errors
from afs_core.errors import (
    AfsError,
    CatalogOnlyError,
    ErrorCode,
    NamespaceNotFoundError,
    NotFoundError,
    QuotaExceededError,
)


def test_not_found_maps_to_404() -> None:
    err = NamespaceNotFoundError("nope")
    assert err.http_status == 404
    assert err.code is ErrorCode.NAMESPACE_NOT_FOUND
    assert isinstance(err, NotFoundError)  # hidden-forbidden disguise


def test_to_problem_is_rfc9457_shaped() -> None:
    err = QuotaExceededError("over limit", detail={"limit_bytes": 1024})
    problem = err.to_problem(instance="/v1/scratch/x")
    assert problem["status"] == 429
    assert problem["code"] == "quota_exceeded"
    assert problem["title"] == "Quota exceeded"
    assert problem["detail"] == "over limit"
    assert problem["instance"] == "/v1/scratch/x"
    assert problem["limit_bytes"] == 1024
    assert problem["type"].endswith("/quota_exceeded")


def test_catalog_only_is_distinct_and_cite_able() -> None:
    err = CatalogOnlyError()
    assert err.code is ErrorCode.CATALOG_ONLY
    assert err.http_status == 422
    assert isinstance(err, AfsError)


def test_every_error_class_has_a_closed_code() -> None:
    valid = set(ErrorCode)
    for name in errors.__all__:
        obj = getattr(errors, name)
        if isinstance(obj, type) and issubclass(obj, AfsError):
            assert obj.code in valid
