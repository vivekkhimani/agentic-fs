# Example: quickstart

The default, near-$0-idle agentic-fs footprint. You apply it from your own
checkout (CI is validate-only and never deploys — see [`../../README.md`](../../README.md)).

**Required inputs:** `aws_account_id` (the target account) and `aws_region`. The
state bucket is account-specific, so it's supplied as partial backend config at
init. Everything else is defaulted.

```bash
cd terraform/examples/quickstart
ACCOUNT_ID=<your-account-id>
terraform init -backend-config="bucket=agentic-fs-terraform-state-${ACCOUNT_ID}"
terraform plan  -var aws_account_id="${ACCOUNT_ID}" -var aws_region=us-east-1
terraform apply -var aws_account_id="${ACCOUNT_ID}" -var aws_region=us-east-1
```

## Composed so far

| Module | Milestone | What it creates |
|---|---|---|
| `kms` | M0 | the project CMK (`alias/<name_prefix>-data`) + key policy |
| `storage` | M0 | the canonical data bucket (`<name_prefix>-data-<account_id>`): versioned, SSE-KMS, TLS-only, lifecycle'd, EventBridge-enabled |
| `catalog_dynamodb` | M1 | the derived catalog table (`<name_prefix>-catalog`): PAY_PER_REQUEST, PITR, deletion protection, SSE-KMS, TTL, 3 GSIs |
| `ecr_mirror` | M1 | the API image repository (`<name_prefix>-api`) |
| `compute_lambda` | M1 | the API Lambda + streaming Function URL + boundary-bound exec role *(gated by `enable_compute`)* |

Outputs: `data_bucket_name`, `kms_key_arn`, `catalog_table_name`,
`ecr_repository_url`, `function_url`, … Later modules (ingestion, auth,
observability) are wired in here milestone-by-milestone
(`docs/agentic-fs-oss-plan.md` §15).

## Deploy the API (compute)

The Lambda runs a container image, so the image must be in ECR **before** the
function is created. Two steps:

```bash
# 1. Create the ECR repo (and the rest of the footprint). Compute is OFF here.
terraform apply -var aws_account_id="${ACCOUNT_ID}" -var aws_region=us-east-1   # enable_compute defaults to false

# 2. Build + push the image to the repo from step 1.
REPO=$(terraform output -raw ecr_repository_url)
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "${REPO%/*}"
docker build --platform linux/amd64 -t "$REPO:0.1.0" ../../..      # repo root Dockerfile
docker push "$REPO:0.1.0"

# 3. Now create the Lambda + Function URL (image_tag defaults to 0.1.0).
terraform apply -var aws_account_id="${ACCOUNT_ID}" -var aws_region=us-east-1 -var enable_compute=true
terraform output function_url
```

The Function URL defaults to **`AWS_IAM`** auth (signed callers only — not
public) because the app still uses dev auth; it flips to `NONE` + app-layer OAuth
once the resource server lands. Verify with a SigV4-signed request:

```bash
URL=$(terraform output -raw function_url)
curl --aws-sigv4 "aws:amz:us-east-1:lambda" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  -H "x-amz-security-token: $AWS_SESSION_TOKEN" "${URL}v1/healthz"
```

> To keep CI safe, `enable_compute` defaults to **false** — flip it to `true`
> (committed) only once the image tag it references is in ECR, so the merge-apply
> never references a missing image.

## Prerequisites

1. [`../../global/bootstrap`](../../global/bootstrap) applied (the state bucket
   this root's backend points at).
2. [`../../global/ci-roles`](../../global/ci-roles) applied (so CI can plan/apply).
3. The `AWS_ACCOUNT_ID` repo secret set and the `sandbox` GitHub Environment
   created (see [`../../README.md`](../../README.md)).

## The other examples

`hardened`, `full`, and `byo-postgres` are documented variants of this same
composition (different flags / module sets). They are doc stubs until the
modules they compose exist.
