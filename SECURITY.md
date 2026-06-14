# Security Policy

## Supported versions

`agentic-fs` is pre-1.0 and under active development. Security fixes are applied
to the `master` branch and the latest published packages
(`afs-core`, `afs-server`, `afs-connector-sdk`). There are no long-term support
branches yet.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

Instead, report privately using one of:

- **GitHub Security Advisories** — preferred. Open a draft advisory via the
  [Security tab](https://github.com/vivekkhimani/agentic-fs/security/advisories/new).
- **Email** — **vivekkhimani07@gmail.com** with the subject line
  `[security] agentic-fs`.

Please include:

- a description of the vulnerability and its impact,
- steps to reproduce or a proof of concept,
- affected component(s) and version/commit, and
- any suggested remediation.

## What to expect

- **Acknowledgement** within 5 business days.
- An assessment and, where applicable, a remediation plan.
- Credit in the release notes / advisory once a fix ships, unless you prefer to
  remain anonymous.

Because `agentic-fs` deploys into **your own AWS account**, many security
properties depend on how you configure IAM, KMS, and networking. The threat
model and deployment guidance live in the docs (`docs/decisions/`); please
review them before deploying to production.

Thank you for helping keep `agentic-fs` and its users safe.
