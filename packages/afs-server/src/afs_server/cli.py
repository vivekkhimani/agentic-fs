"""``afs`` — the server-side admin CLI (Click).

Today it ships one command, ``afs auth doctor``: paste a bearer token and see how
this resource server validates it and what principal it maps to (ADR 0013). It's
the fast way to wire up your own IdP — the usual "why is my token rejected / why
are my scopes empty" questions answered in one shot, against the *real* verifier.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import TYPE_CHECKING, Any, TextIO

import click

from afs_core.errors import AfsError
from afs_server.auth import build_token_verifier, context_from_claims, resolve_dev_context
from afs_server.settings import load_settings

if TYPE_CHECKING:
    from afs_server.settings import Settings


def _decode_unverified(token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Header + claims, WITHOUT verifying — so we can show what's in the token
    even when verification fails (the whole point of a doctor)."""
    import jwt  # PyJWT

    header = jwt.get_unverified_header(token)
    claims = jwt.decode(token, options={"verify_signature": False})
    return header, claims


def _failure_hint(claims: dict[str, Any], settings: Settings) -> str:
    """Best-effort reason a token failed, from the unverified claims vs config."""
    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and exp < time.time():
        return "token is expired (exp is in the past)"
    aud = claims.get("aud")
    want_aud = settings.oidc_audience
    if want_aud and aud not in (want_aud, [want_aud]) and want_aud not in (aud or []):
        return f"audience mismatch: token aud={aud!r}, this server expects {want_aud!r}"
    iss = claims.get("iss")
    if settings.oidc_issuer and iss != settings.oidc_issuer:
        return f"issuer mismatch: token iss={iss!r}, this server expects {settings.oidc_issuer!r}"
    return "signature did not validate — wrong signing key / JWKS, or wrong algorithm"


def _print_config(settings: Settings, out: TextIO) -> None:
    p = lambda *a: print(*a, file=out)  # noqa: E731
    p("auth_mode:", settings.auth_mode)
    if settings.auth_mode != "oidc":
        return
    key = (
        "public_key (static-jwt)"
        if settings.oidc_public_key
        else (settings.oidc_jwks_uri or "(derived from issuer)")
    )
    p("issuer:   ", settings.oidc_issuer or "(unset)")
    p("keys:     ", key)
    p("audience: ", settings.oidc_audience or "(unset — not enforced)")
    p(
        f"claim map: principal={settings.oidc_principal_claim} "
        f"tenant={settings.oidc_tenant_claim} scopes={settings.oidc_scopes_claim} "
        f"namespaces={settings.oidc_namespaces_claim}"
    )
    p(
        f"defaults:  tenant={settings.oidc_default_tenant or '(none)'} "
        f"namespaces={settings.oidc_default_namespaces or '(none)'}"
    )


def _describe_namespaces(ns: frozenset[str] | None) -> str:
    if ns is None:
        return "TENANT-WIDE (all namespaces in the tenant)"
    if not ns:
        return "DENY-ALL (no claim and no default — this principal sees nothing)"
    return "{" + ", ".join(sorted(ns)) + "}"


def run_doctor(settings: Settings, token: str | None, out: TextIO) -> int:
    """Diagnose token validation + claim mapping. Returns a process exit code."""
    p = lambda *a: print(*a, file=out)  # noqa: E731
    p("afs auth doctor")
    p("=" * 40)
    _print_config(settings, out)

    if settings.auth_mode == "dev":
        ctx = resolve_dev_context(settings)
        p("\ndev mode: a STATIC principal, no token verification (never production).")
        p(f"  tenant_id={ctx.tenant_id} principal_id={ctx.principal_id}")
        p(f"  scopes={sorted(ctx.scopes)}")
        return 0

    try:
        verifier = build_token_verifier(settings)
    except AfsError as err:
        p(f"\nconfig error: {err.message}")
        return 2
    if token is None:
        p("\nno token provided — pass one via --token or stdin to test verification.")
        return 2

    header, claims = _decode_unverified(token)
    p("\nToken (unverified decode):")
    p("  header:", json.dumps(header))
    p("  claims:", json.dumps(claims, indent=2, default=str, sort_keys=True))

    access = asyncio.run(verifier.verify_token(token))
    if access is None:
        p(f"\nVerification: FAIL — {_failure_hint(claims, settings)}")
        return 1
    p("\nVerification: PASS (signature, iss, aud, exp all valid)")

    try:
        ctx = context_from_claims(access.claims, settings)
    except AfsError as err:
        p(f"\nClaim mapping FAILED: {err.message}")
        return 1
    p("\nResolved TenantContext:")
    p(f"  tenant_id:    {ctx.tenant_id}   (claim {settings.oidc_tenant_claim!r})")
    p(f"  principal_id: {ctx.principal_id}   (claim {settings.oidc_principal_claim!r})")
    p(f"  scopes:       {sorted(ctx.scopes) or '∅ (claim absent → no capabilities)'}")
    p(f"  namespaces:   {_describe_namespaces(ctx.namespaces)}")
    return 0


def _resolve_token(token: str | None) -> str | None:
    """--token VALUE, or '-'/absent → read from stdin (so you can pipe a token)."""
    if token and token != "-":
        return token
    if not sys.stdin.isatty():
        piped = sys.stdin.read().strip()
        return piped or None
    return None


@click.group()
@click.version_option(package_name="afs-server", prog_name="afs")
def main() -> None:
    """agentic-fs admin CLI."""


@main.group()
def auth() -> None:
    """Authentication helpers."""


@auth.command()
@click.option("--token", default=None, help="Bearer token to inspect (or pipe via stdin).")
def doctor(token: str | None) -> None:
    """Diagnose token validation + claim mapping against this server's config."""
    code = run_doctor(load_settings(), _resolve_token(token), sys.stdout)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
