"""Google Drive connector — crawl a Drive folder tree into agentic-fs.

Source-side auth is per-user OAuth (the installed-app flow): point it at an OAuth
client-secrets file once, consent in the browser, and the refresh token is cached
for later runs. Google-native docs (Docs / Sheets / Slides) are **exported** to
Office formats so the `text_native` / `docling` rungs can read them. Needs the
``[gdrive]`` extra.

Incremental: each file carries Drive's monotonic ``version`` as its change token,
so a re-sync skips the (expensive) re-download of unchanged files via the engine's
L1 path (ADR 0008). The delta ``changes.list`` path (L2) is a planned follow-up;
this version is a full-scan `Connector`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from afs_core.models import SourceItem

_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
_FOLDER_MIME = "application/vnd.google-apps.folder"

# Google-native type -> (export MIME, filename extension). Native docs aren't
# downloadable as-is; they're exported to a readable format.
_EXPORT = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
}
_LIST_FIELDS = "nextPageToken, files(id, name, mimeType, size, version, modifiedTime)"


class GDriveConnector:
    name = "gdrive"

    def __init__(
        self,
        source: str = "root",
        *,
        credentials: str = "",
        token: str = "",
        export_pdf: str = "false",
        service: Any = None,
    ) -> None:
        # `source` is a folder id (or "root" for My Drive). `service` is injected
        # in tests; in production it's built from the OAuth client-secrets file.
        self._root = source or "root"
        self._export_pdf = str(export_pdf).lower() in {"1", "true", "yes"}
        self._service = service if service is not None else _build_service(credentials, token)

    def discover(self) -> Iterator[SourceItem]:
        yield from self._walk(self._root, "")

    def _walk(self, folder_id: str, prefix: str) -> Iterator[SourceItem]:
        for f in self._children(folder_id):
            if f["mimeType"] == _FOLDER_MIME:
                yield from self._walk(f["id"], f"{prefix}{f['name']}/")
            else:
                yield self._to_item(f, prefix)

    def _children(self, folder_id: str) -> Iterator[dict]:
        page: str | None = None
        while True:
            resp = (
                self._service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    fields=_LIST_FIELDS,
                    pageSize=1000,
                    pageToken=page,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            yield from resp.get("files", [])
            page = resp.get("nextPageToken")
            if not page:
                return

    def _to_item(self, f: dict, prefix: str) -> SourceItem:
        export_mime, ext = _EXPORT.get(f["mimeType"], (None, ""))
        if export_mime and self._export_pdf:
            export_mime, ext = "application/pdf", ".pdf"
        name = f["name"]
        if ext and not name.endswith(ext):
            name += ext
        return SourceItem(
            path=f"{prefix}{name}",
            # locator carries the file id + (optional) export MIME for fetch().
            locator=f"{f['id']}\t{export_mime or ''}",
            size=int(f["size"]) if f.get("size") else None,
            content_type=export_mime or f["mimeType"],
            version=str(f.get("version") or f.get("modifiedTime") or "") or None,
        )

    def fetch(self, item: SourceItem) -> bytes:
        file_id, _, export_mime = item.locator.partition("\t")
        files = self._service.files()
        if export_mime:
            return files.export_media(fileId=file_id, mimeType=export_mime).execute()
        return files.get_media(fileId=file_id, supportsAllDrives=True).execute()


def _build_service(credentials: str, token: str) -> Any:
    import os.path

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ModuleNotFoundError as err:  # pragma: no cover - import guard
        raise RuntimeError(
            "the gdrive connector needs the optional extra: pip install 'afs-connector-sdk[gdrive]'"
        ) from err

    token = os.path.expanduser(token or "~/.config/agentic-fs/gdrive-token.json")
    credentials = os.path.expanduser(credentials or "~/.config/agentic-fs/gdrive-client.json")

    creds = None
    if os.path.exists(token):
        creds = Credentials.from_authorized_user_file(token, _SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials, _SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(token), exist_ok=True)
        with open(token, "w") as fh:
            fh.write(creds.to_json())
    return build("drive", "v3", credentials=creds, cache_discovery=False)
