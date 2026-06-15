# web/ — agentic-fs landing site

A minimal, zero-build static landing page and the AWS hosting for it. Lives in the
monorepo (nothing sensitive); deploys independently of the library/infra.

```
web/
  site/     the static site: index.html + styles.css (no build, no JS)
  infra/    Terraform for hosting (S3 + CloudFront + ACM + Route 53)
```

## Hosting

S3 (private) → CloudFront (OAC + TLS via ACM) → Route 53 alias records. The ACM
cert lives in `us-east-1` (a CloudFront requirement) and is DNS-validated in the
hosted zone. Set the apex in `infra/variables.tf` (`domain`, default
`agenticfs.xyz`).

### DNS (one-time, per deployer)

1. Create a **public Route 53 hosted zone** for your domain (Route 53 console, or
   `aws route53 create-hosted-zone --name <domain> --caller-reference $(date +%s)`).
2. At your registrar, set the domain's **nameservers** to the four `awsdns-*`
   servers the new zone shows (drop the trailing dots).

The Terraform references the zone as a **data source** by domain name; it does not
create or own it, so the zone (and the live site) survive an agentic-fs teardown.

## Apply + deploy

```bash
cd web/infra
terraform init && terraform apply        # cert + CloudFront + alias records
# then publish the page:
aws s3 sync ../site/ "s3://$(terraform output -raw site_bucket)/" --delete
aws cloudfront create-invalidation --distribution-id "$(terraform output -raw distribution_id)" --paths '/*'
```

CI deploy is **owner-gated** (`.github/workflows/web.yml`: `workflow_dispatch` +
`repository_owner` guard) using a narrow OIDC role scoped to just the site bucket
+ CloudFront invalidation, so it doesn't reintroduce broad account access. It
reads the repo variables `SITE_AWS_ACCOUNT_ID`, `SITE_BUCKET`,
`SITE_DISTRIBUTION_ID` (set from the `terraform output`s above).

## Editing the site

One page: edit `site/index.html` (content) and `site/styles.css` (theme). No build
step; preview by opening `site/index.html` in a browser.
