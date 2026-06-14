# ADR 0013: authentication — an IdP-agnostic OAuth 2.1 resource server (M4)

**Status:** accepted · **Date:** 2026-06-14

## Context

Everything today runs as a static **dev principal** with all scopes
(`resolve_context(settings)` reads only settings; `auth_mode` has an `oidc`
placeholder that fails closed). The scope enforcement, namespace gating, and
multi-tenancy built in M3 ([ADR 0012](0012-mcp-tools-and-middleware.md)) are
therefore wired but never exercised by real auth. This is the load-bearing gap.

The MCP spec (2025-11-25) formally classifies an MCP server as an **OAuth 2.1
resource server**: it *accepts and validates* access tokens, advertises where to
get them (`WWW-Authenticate` → Protected Resource Metadata, RFC 9728), and relies
on RFC 8707 resource binding — it does **not** issue tokens. We want agentic-fs
usable by us (Seamind, on WorkOS) **and** by external orgs on their own IdPs
(Cognito, Auth0, Okta, Keycloak, …), and reachable from arbitrary MCP clients.

Two categories of OSS exist and the distinction decides the design:
- **Authorization servers / IdPs** (`mcp-oauth`, MCP-Nest's built-in AS; Keycloak,
  Zitadel, Ory, Authentik) — these *issue* tokens. We use none of them as a
  dependency: owning or embedding an AS is lock-in and a security surface we
  shouldn't carry.
- **Resource-server / token validation** — FastMCP's built-in verifiers
  (`JWTVerifier`, `RemoteAuthProvider`) already in our stack, and Authlib for the
  REST side. We adopt from here.

## Decision

**agentic-fs is a pure, IdP-agnostic OAuth 2.1 resource server. Bring your own
IdP.** We validate tokens and map their claims; we never issue them, and the auth
*client* (obtaining a token) is the calling app's job — the standard MCP model.

### Token validation (delegated)

- The MCP mount is wrapped in FastMCP's `RemoteAuthProvider` over a `JWTVerifier`
  configured from the issuer — JWKS fetch/cache/rotation, signature, `iss`, `aud`,
  `exp`/`nbf`, and required scopes are the library's job. `RemoteAuthProvider`
  also serves `/.well-known/oauth-protected-resource`, so MCP clients self-discover
  the authorization server with **zero custom client code**.
- The **same verifier** is reused by a FastAPI bearer dependency on the REST
  routes, so MCP and REST share one validation path (no second implementation).
- RFC 8707 audience/resource binding is enforced (`AFS_OIDC_AUDIENCE`) to prevent
  token passthrough / confused-deputy.

### Claims → `TenantContext` (the only part we own)

Stateless and flat — both forks resolved toward "pure OAuth, no state we manage":

- **Scopes: trust the token directly.** The token's `scope`/`scp` claim must
  already carry our vocabulary (`fs:read`, `fs:search`, `fs:write:scratch`,
  `ingest`, `admin`). No role→scope mapping layer for us to own or drift. The
  developer registers these scopes in their IdP's API/resource config (recipes
  provided). *(Rejected: mapping IdP roles/groups → scopes — defers to a future
  optional mapper if demand appears.)*
- **Namespaces: from a token claim.** `TenantContext.namespaces` comes from a
  configurable claim (default `afs_namespaces`). Stateless, no grant store, and an
  external org controls access entirely in its own IdP. *(Rejected: a
  catalog-managed grant store + admin API — more control, but a stateful concern
  to heal/secure and an admin surface we'd own; revisit only if a deployment needs
  central grant management.)*
- **Principal/tenant** from configurable claims: `sub` → `principal_id` (default);
  a configurable tenant claim (`AFS_OIDC_TENANT_CLAIM`, e.g. WorkOS `org_id`,
  Cognito `custom:tenant_id`) → `tenant_id`.
- **`resolve_context` becomes request-aware**: it reads the verified token off the
  request instead of synthesizing a static principal. This is the seam that
  *activates* M3's enforcement; `dev` mode keeps returning the static principal.
- An **optional** pluggable claims mapper (`afs.claims_mappers` entry-point, the
  ADR 0002 pattern) is the escape hatch for non-flat mappings — not on the core
  path, since flat claim names + trusted scopes cover the common case.

### Developer experience — "point, map, go"

Hooking up an IdP is the headline DX. Happy path is three env vars
(`AFS_AUTH_MODE=oidc`, `AFS_OIDC_ISSUER`, `AFS_OIDC_AUDIENCE`); the JWKS URI and
algorithms come from OIDC discovery. Claim names are overridable for the bits that
differ per IdP. Beyond config we ship:

1. **`afs auth doctor`** — paste a token; it runs the *real* validation against the
   configured issuer and prints the decoded claims **and** the resulting
   `TenantContext` (tenant/principal/scopes/namespaces). Turns the usual "why is my
   token rejected / why are my scopes empty" black box into a 30-second check.
2. **Auto-served Protected Resource Metadata** (above) — MCP clients need no auth
   code.
3. **Per-IdP recipe pages** (WorkOS, Cognito, Auth0, Okta, Keycloak): copy-paste
   env blocks, since "which claim is what" is the only real variable.
4. **Local without an IdP**: keep `dev` mode, plus a `static-jwt` debug verifier
   (a configured public key, no network) so people can test the full path offline.
5. **Spec-correct failures**: `401` with `WWW-Authenticate` pointing at the AS, and
   structured reasons (bad `aud`, expired, missing claim).

### Cognito is one optional module, not the design

`auth_cognito` (a Terraform module provisioning a user pool + resource server +
scopes) is **optional**, for greenfield users with no IdP — the only audience for
it. It outputs issuer/audience to feed the same settings. It is never on the core
path; BYO-IdP (us on WorkOS, others on theirs) needs no module.

## Why

- **No lock-in, no AS to own.** We delegate issuance to mature IdPs; our surface is
  validation + a thin claim map. Works for our WorkOS setup and any external org's.
- **Standards = free interop.** Resource-server + RFC 9728/8707 means MCP clients
  (Claude, etc.) authenticate with no custom code.
- **Stateless by choice.** Token-claim namespaces + trusted scopes mean no new
  store, nothing extra to heal or secure — consistent with ~$2/mo idle and
  "S3 is canonical."
- **Activates M3.** A request-aware `resolve_context` makes the scope/namespace
  enforcement and tenant isolation real; the M3 tests flip from theoretical to
  live.
- **Same seams as the rest.** Entry-point pluggability (ADR 0002), one shared
  service path (no self-calls), structlog audit (ADR 0009).

## Consequences

- `resolve_context` signature changes to be request-aware; both REST and MCP call
  sites thread the request/verified token. `dev` mode is preserved for local.
- Developers must register our scope vocabulary in their IdP (documented per-IdP).
  If that proves a friction point, the optional role→scope mapper is the additive
  fix — no redesign.
- Namespace access lives in the IdP's token; central grant management is out of
  scope until a deployment demands it (additive: a catalog-grants claims mapper).
- New config knobs (`AFS_OIDC_*`) and a `static-jwt`/`dev` mode matrix to document
  and test (test tokens minted from a local RSA keypair — no live IdP in CI).

## Slices

1. **This ADR.**
2. **Core verifier + claims mapping** — `auth_mode="oidc"`, `AFS_OIDC_*` settings,
   claims→`TenantContext`, fails closed; unit-tested with a local RSA keypair.
3. **Wire both surfaces** — `RemoteAuthProvider` on MCP, FastAPI bearer dep on
   REST, request-aware `resolve_context`; tenant-isolation + scope-denial tests go
   live. `afs auth doctor` + `static-jwt` mode.
4. **Optional** — `auth_cognito` module + example wiring + the "bring your own IdP"
   swap-guide with per-IdP recipes.

## References

- MCP Authorization spec (2025-11-25) — resource-server classification, RFC 9728
  Protected Resource Metadata, RFC 8707 resource indicators.
- FastMCP auth: `RemoteAuthProvider`, `JWTVerifier`, ready providers (`workos`,
  `aws`/Cognito, `auth0`, `keycloak`, …).
- [ADR 0002](0002-pluggable-backends-via-entry-points.md) (entry-point pluggability),
  [ADR 0012](0012-mcp-tools-and-middleware.md) (scopes/namespaces the middleware enforces).
