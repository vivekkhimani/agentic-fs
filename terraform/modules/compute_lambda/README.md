# `compute_lambda` — API Lambda (default serving compute)

Runs the API container image as a Lambda behind a **streaming Function URL**. The
image (one image for Lambda + Fargate, [ADR 0003](../../../docs/decisions/0003-container-image.md))
bridges Function URL invocations to the ASGI app via the AWS Lambda Web Adapter.

This is the **first IAM-role-creating module**, so its exec role sets
`permissions_boundary` — the CI apply role's own boundary *denies* creating a
role without it (escalation prevention, `terraform/DECISIONS.md` §2a).

## Resources

- `aws_lambda_function.api` — `<name_prefix>-api`, `package_type=Image`.
- `aws_lambda_function_url.api` — `RESPONSE_STREAM`; auth `AWS_IAM` by default.
- `aws_iam_role.exec` (+ boundary) + least-privilege policy: scoped logs, S3 read
  on the data bucket, DynamoDB read on the catalog + its indexes, `kms:Decrypt`
  on the project CMK.
- `aws_cloudwatch_log_group.api`.

## Inputs (selected)

| Name | Default | Description |
|---|---|---|
| `image_uri` | — | ECR image URI to run. |
| `permissions_boundary_arn` | — | Boundary for the exec role (required). |
| `function_url_auth_type` | `AWS_IAM` | `AWS_IAM` (signed callers only) or `NONE` (public — only once app-layer OAuth exists). |
| `auth_mode` | `dev` | `AFS_AUTH_MODE` for the app. |
| `memory_mb` / `timeout_seconds` | `1024` / `30` | Function sizing. |

## Outputs

`function_url`, `function_name`, `function_arn`, `exec_role_arn`.

## Security notes

- **Function URL auth.** Defaults to `AWS_IAM` (not public) because the app only
  has dev auth today. Flip to `NONE` + app-layer OAuth once the resource server
  lands — never expose `NONE` while `auth_mode=dev`.
- The exec role is read-only (the deployed surface is the read path); ingestion's
  write permissions are added when that path deploys.
