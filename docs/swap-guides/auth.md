# Swap guide: bring your own IdP (OAuth 2.1)

agentic-fs is an OAuth 2.1 **resource server** ([ADR 0013](../decisions/0013-auth-oauth-resource-server.md)):
it **validates** bearer JWTs from *your* identity provider and maps their claims to
a principal. It never issues tokens — your app/agent gets a token from your IdP
the normal way and sends it. So "hooking up auth" is **config, not code**.

## The happy path

```bash
AFS_AUTH_MODE=oidc
AFS_OIDC_ISSUER=https://your-idp.example.com   # OIDC issuer
AFS_OIDC_JWKS_URI=https://your-idp.example.com/.well-known/jwks.json
AFS_OIDC_AUDIENCE=agentic-fs                    # RFC 8707 resource binding
```

Then map the claims that differ per IdP (defaults shown):

```bash
AFS_OIDC_PRINCIPAL_CLAIM=sub          # → principal_id
AFS_OIDC_TENANT_CLAIM=tenant_id       # → tenant_id (isolation boundary)
AFS_OIDC_SCOPES_CLAIM=scope           # → scopes (trusted from the token)
AFS_OIDC_NAMESPACES_CLAIM=afs_namespaces   # → granted namespaces
```

Two stateless rules ([ADR 0013](../decisions/0013-auth-oauth-resource-server.md)):

- **Scopes are trusted from the token.** The scopes claim must carry our
  vocabulary: `fs:read`, `fs:search`, `fs:write:scratch`, `ingest`, `admin`.
- **Namespaces are the data boundary and fail safe.** An absent namespaces claim
  **denies all namespaces**. Opt into a default with
  `AFS_OIDC_DEFAULT_NAMESPACES=*` (tenant-wide) or a list; the claim may also be
  `*` for per-token tenant-wide. `tenant_id` always isolates regardless.
- Single-tenant IdP with no tenant claim? Set `AFS_OIDC_DEFAULT_TENANT`.

## Check it in one shot

```bash
afs auth doctor --token "<paste a real token>"     # or pipe it via stdin
```

It runs the *real* verifier and prints the decoded claims **and** the resolved
principal (tenant / scopes / namespaces) — or a precise failure (expired, audience
mismatch, wrong signing key). Use it before wiring any agent.

MCP clients need **zero** auth code: under `oidc` the mount serves OAuth Protected
Resource Metadata (RFC 9728) at `/.well-known/oauth-protected-resource`, so a
compliant client discovers your authorization server automatically.

## Recipes

### WorkOS

WorkOS access tokens carry `sub`, `org_id`, `role`, `permissions`, `iss`, `exp`;
the JWKS is at `https://api.workos.com/sso/jwks/<client_id>`.

```bash
AFS_AUTH_MODE=oidc
AFS_OIDC_JWKS_URI=https://api.workos.com/sso/jwks/<client_id>   # RS256
AFS_OIDC_TENANT_CLAIM=org_id          # WorkOS organization → tenant
AFS_OIDC_SCOPES_CLAIM=permissions     # WorkOS role permissions → scopes
AFS_OIDC_DEFAULT_NAMESPACES=*         # single-org: org-wide (org_id still isolates)
# Audience + issuer: see the two token types below.
```

WorkOS issues **two** token shapes, and which you validate matters:

- **Session tokens** (AuthKit web sessions, what a BFF attaches to API calls) have
  **no `aud` claim** — leave `AFS_OIDC_AUDIENCE` unset (don't enforce audience) and
  `AFS_OIDC_ISSUER` unset or the WorkOS issuer. Fine for a quick check.
- **Resource-bound tokens** (AuthKit OAuth, the MCP/RFC-8707 flow) carry
  `aud` = your resource URI and `iss` = your **AuthKit domain** (e.g.
  `https://auth.your.app`, *not* `api.workos.com`). For an MCP resource server like
  agentic-fs, prefer these: set `AFS_OIDC_AUDIENCE=<your resource URI>` and
  `AFS_OIDC_ISSUER=<AuthKit domain>`.

Name your WorkOS role **permissions** exactly `fs:read`, `ingest`, … so they land
as our scopes. **Namespaces:** WorkOS custom JWT-template claims are best avoided
(template drift / PII / bloat), so don't push an `afs_namespaces` claim — use
`AFS_OIDC_DEFAULT_NAMESPACES=*` (org-wide, still isolated by `org_id`); reach for
real segmentation only if a deployment needs it. Confirm the live claim shape with
`afs auth doctor` against a real token.

### Amazon Cognito

```bash
AFS_OIDC_ISSUER=https://cognito-idp.<region>.amazonaws.com/<pool_id>
AFS_OIDC_JWKS_URI=$AFS_OIDC_ISSUER/.well-known/jwks.json
AFS_OIDC_AUDIENCE=<app_client_id>
AFS_OIDC_TENANT_CLAIM=custom:tenant_id
AFS_OIDC_SCOPES_CLAIM=scope           # define a Cognito resource server + scopes
```

### Auth0

```bash
AFS_OIDC_ISSUER=https://<tenant>.us.auth0.com/
AFS_OIDC_JWKS_URI=https://<tenant>.us.auth0.com/.well-known/jwks.json
AFS_OIDC_AUDIENCE=https://agentic-fs                # the API Identifier
AFS_OIDC_TENANT_CLAIM=https://agentic-fs/tenant     # a custom (namespaced) claim
AFS_OIDC_NAMESPACES_CLAIM=https://agentic-fs/namespaces
```

### Okta / Keycloak / any OIDC

Point `ISSUER` + `JWKS_URI` + `AUDIENCE` at the provider, define an API/resource
that issues our scopes in the scopes claim, and (optionally) emit a namespaces
claim. `afs auth doctor` tells you what's actually in the token.

## Local / offline (no IdP)

- **dev** (`AFS_AUTH_MODE=dev`) — a static all-scopes principal. Never production.
- **static-jwt** — `AFS_AUTH_MODE=oidc` with `AFS_OIDC_PUBLIC_KEY=<PEM>` instead
  of a JWKS URI: the full validation + mapping path, verified against a key you
  hold. Useful for tests and air-gapped runs.
