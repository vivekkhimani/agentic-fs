# marketing/ — agentic-fs landing site (agenticfs.xyz)

A minimal, zero-build static landing page and the AWS hosting for it. Lives in the
monorepo (nothing sensitive); deploys independently of the library/infra.

```
marketing/
  site/     the static site — index.html + styles.css (no build, no JS)
  infra/    Terraform for hosting (S3 + CloudFront + ACM + Route 53)   [next]
```

## Hosting plan

S3 (private) → CloudFront (OAC + TLS via ACM) → Route 53 alias records, for
`agenticfs.xyz` (+ `www`). The ACM cert lives in `us-east-1` (CloudFront
requirement) and is DNS-validated in the hosted zone.

### DNS (done / your step)

The public hosted zone for `agenticfs.xyz` is created in Route 53
(zone `Z09095461O6AGUQZHS8YG`). Point GoDaddy's nameservers at it (Domain →
Manage DNS → Nameservers → "I'll use my own", drop trailing dots):

```
ns-553.awsdns-05.net
ns-132.awsdns-16.com
ns-1480.awsdns-57.org
ns-1610.awsdns-09.co.uk
```

The Terraform references this zone as a **data source** (it does not create it),
so the zone survives independent of any agentic-fs teardown.

## Deploy

CI deploy is **owner-gated** (`workflow_dispatch`, `repository_owner` guard) using
a narrow OIDC role scoped to just the site bucket + CloudFront invalidation — it
does not reintroduce broad account access. Locally:

```bash
aws s3 sync marketing/site/ "s3://<site-bucket>/" --delete
aws cloudfront create-invalidation --distribution-id <id> --paths '/*'
```

## Editing the site

It's one page — edit `site/index.html` (content) and `site/styles.css` (the
dev-indie theme). No build step; preview by opening `site/index.html` in a browser.
