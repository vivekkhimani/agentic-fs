# Google Drive connector

Crawl a Google Drive folder into agentic-fs. Google-native docs (Docs / Sheets /
Slides) are exported to Office formats so the extraction rungs can read them.

```bash
pip install "afs-connector-sdk[gdrive]"
```

## One-time GCP setup

1. **Project** — create or reuse one at <https://console.cloud.google.com>.
2. **Enable the Drive API** — APIs & Services → Library → *Google Drive API* → Enable.
3. **OAuth consent screen** — User type *External* (or *Internal* on Workspace);
   add the scope `https://www.googleapis.com/auth/drive.readonly`; while the app
   is in *Testing*, add your account under *Test users*.
4. **OAuth client** — Credentials → Create credentials → OAuth client ID →
   **Desktop app** → download the JSON (the client-secrets file).

The connector reads only with `drive.readonly`. The refresh token is obtained via
the browser consent flow on first run and cached at
`~/.config/agentic-fs/gdrive-token.json` — it is never committed or sent anywhere
but Google.

## Run

```bash
# First run opens a browser for consent; later runs reuse the cached token.
fs-crawler --connector gdrive \
  --source <FOLDER_ID> \                      # or "root" for My Drive
  --opt credentials=/path/to/client_secret.json \
  --api-url "$FUNCTION_URL" --namespace drive --auth sigv4 --region us-east-1
```

Options (`--opt key=value`): `credentials` (client-secrets path),
`token` (token cache path), `export_pdf=true` (export native docs to PDF instead
of Office). The folder id is the last path segment of the Drive URL
(`drive.google.com/drive/folders/<FOLDER_ID>`).

## Incremental

Each file carries Drive's `version` as its change token, so a re-sync **skips the
re-download** of unchanged files (engine L1, [ADR 0008](../decisions/0008-incremental-sync.md)).
The delta `changes.list` path (L2 — enumerate only what changed) is the planned
next step; today the connector is a full-scan `Connector`.
