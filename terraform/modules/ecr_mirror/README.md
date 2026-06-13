# `ecr_mirror` — ECR repository for the API image

Private ECR repository the API container image is pushed to. Lambda can only
pull images from same-account ECR, so this is where the published image lives.

## Resources

- `aws_ecr_repository.api` — `<name_prefix>-api`, scan-on-push, AES256.
- `aws_ecr_lifecycle_policy.api` — expire untagged images after N days.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `name_prefix` | string | — | Repo name prefix (`<name_prefix>-api`). |
| `untagged_expiry_days` | number | `14` | Expire untagged images after N days. |

## Outputs

| Name | Description |
|---|---|
| `repository_url` | Push images here; the Lambda pulls from it. |
| `repository_arn` | Repository ARN. |

## Deferred

The "mirror upstream pinned images" half of the original contract (copying
published base/runtime images into this account) is deferred — this module
implements the repo the API image uses.
