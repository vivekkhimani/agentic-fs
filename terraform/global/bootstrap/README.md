# Terraform state backend (bootstrap)

One-time setup that creates the S3 bucket every other agentic-fs Terraform root
uses as its remote backend. **Run this once per account, by a human with admin
credentials**, before any root can `terraform init` against the S3 backend.

State locking is handled by S3 natively (`use_lockfile = true`, Terraform
>= 1.10) — there is no DynamoDB lock table to create.

It runs in your AWS account; everything it creates is `agentic-fs-*`-named and
`Project = agentic-fs`-tagged, so it stays cleanly separable from any other
infrastructure sharing the account.

## First-time setup

```bash
cd terraform/global/bootstrap

# 1. Authenticate to the AWS account with admin credentials (this creates an
#    S3 bucket that all later roots depend on).
#    e.g. aws sso login --profile agentic-fs-admin && export AWS_PROFILE=agentic-fs-admin

# 2. Create the bucket with LOCAL state.
terraform init
terraform plan      # review: one bucket + its config resources, nothing else
terraform apply

# 3. Migrate bootstrap's own state INTO the bucket it just created:
#    uncomment the `backend "s3"` block in terraform.tf, then:
terraform init -migrate-state
```

After step 3, delete the local `terraform.tfstate*` files — the source of
truth now lives in the bucket under `global/bootstrap.tfstate`.

## What it creates

| Resource | Purpose |
|---|---|
| `aws_s3_bucket.tf_state` | Holds all remote state. `prevent_destroy = true`. |
| versioning | Roll back a corrupted/truncated state push. |
| SSE (AES256) | Encrypt state at rest — it will contain secret values as modules land. |
| public access block | State is never public. |
| lifecycle | Expire noncurrent versions after 90d; abort stale MPUs. |
| bucket policy | Deny non-TLS access. |

## Why this is separate from the rest

The bucket must exist *before* any other root can configure its `backend "s3"`.
Keeping bootstrap in its own root with its own (self-hosted, after step 3) state
avoids that circular dependency cleanly.

## Next

Once the bucket exists, apply [`../ci-roles`](../ci-roles) (the GitHub-OIDC
plan/apply identities) so the pipeline can assume into the account.
