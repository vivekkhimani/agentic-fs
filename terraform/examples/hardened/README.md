# Example: hardened

The quickstart footprint with **defense-in-depth turned on**, using the modules
implemented today. You apply it from your own checkout (CI is validate-only).

```bash
cd terraform/examples/hardened
ACCOUNT_ID=<your-account-id>
terraform init  -backend-config="bucket=agentic-fs-terraform-state-${ACCOUNT_ID}"
terraform apply -var aws_account_id="${ACCOUNT_ID}" -var aws_region=us-east-1 \
                -var alarm_email=ops@example.com
```

## On now vs the headline model

What's **on now** (implemented modules):
- CMK deletion window maxed (30d); SSE-KMS everywhere.
- Catalog: **deletion protection + point-in-time recovery** ON.
- Function URL is **`AWS_IAM`** only (signed callers — never `NONE`); app auth is
  the **OIDC resource server** (`auth_mode = oidc`).
- High-signal CloudWatch alarms with an email subscription.

What's **deliberately not faked** — these need modules still to be built, and are
tracked as contribution issues (PRs welcome):

| Hardening | Module (to build) |
|---|---|
| S3 malware scan + quarantine gate | `security_guardduty` |
| Object-level S3 access logging | `storage` access-logs bucket |
| Private subnets / NAT, no public URL | `network` + `compute_fargate` |
| Per-request STS session scoping (Layer-2 isolation) | app + `ci-roles` |

When a module lands, it slots into `main.tf` the same way the implemented modules
are composed. See `docs/agentic-fs-oss-plan.md` §4 and §11 for the hardening model.
