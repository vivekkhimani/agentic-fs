"""Google Drive connector against a faked Drive service (no live calls).

Covers the parts that are *our* logic — folder-tree paths, native-doc export
mapping, the export-vs-download fetch dispatch, and the version change-token —
certified by the afs-core kit. The OAuth flow and real API shape are validated
live with real credentials.
"""

from __future__ import annotations

import pytest

from afs_connector_sdk.connectors.gdrive import GDriveConnector
from afs_core.testing import ConnectorConformance

_DOC = "application/vnd.google-apps.document"
_FOLDER = "application/vnd.google-apps.folder"
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# A tiny Drive: root has a markdown file, a native Doc, and a "Reports" folder
# containing a text file.
_DRIVE = {
    "root": [
        {"id": "f1", "name": "notes.md", "mimeType": "text/markdown", "size": "5", "version": "7"},
        {"id": "d1", "name": "Plan", "mimeType": _DOC, "version": "3"},
        {"id": "fold1", "name": "Reports", "mimeType": _FOLDER, "version": "1"},
    ],
    "fold1": [
        {"id": "f2", "name": "q1.txt", "mimeType": "text/plain", "size": "4", "version": "2"},
    ],
}
_MEDIA = {"f1": b"hello", "f2": b"data", "d1": b"<docx-bytes>"}


class _Exec:
    def __init__(self, value: object) -> None:
        self._value = value

    def execute(self) -> object:
        return self._value


class _FakeFiles:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list(self, *, q: str, pageToken: str | None = None, **_: object) -> _Exec:
        folder_id = q.split("'")[1]  # "'<id>' in parents and trashed = false"
        return _Exec({"files": _DRIVE.get(folder_id, [])})

    def get_media(self, *, fileId: str, **_: object) -> _Exec:
        self.calls.append(f"get_media:{fileId}")
        return _Exec(_MEDIA[fileId])

    def export_media(self, *, fileId: str, mimeType: str, **_: object) -> _Exec:
        self.calls.append(f"export:{fileId}:{mimeType}")
        return _Exec(_MEDIA[fileId])


class _FakeService:
    def __init__(self) -> None:
        self._files = _FakeFiles()

    def files(self) -> _FakeFiles:
        return self._files


def _connector(**kw: str) -> GDriveConnector:
    return GDriveConnector("root", service=_FakeService(), **kw)


class TestGDriveConnector(ConnectorConformance):
    @pytest.fixture
    def connector(self) -> GDriveConnector:
        return _connector()


def test_walks_tree_into_relative_paths() -> None:
    paths = {i.path for i in _connector().discover()}
    assert paths == {"notes.md", "Plan.docx", "Reports/q1.txt"}


def test_native_doc_is_exported_to_office() -> None:
    plan = next(i for i in _connector().discover() if i.path == "Plan.docx")
    assert plan.content_type == _DOCX
    assert plan.version == "3"  # the change token rides along (drives L1 skip)


def test_export_pdf_option() -> None:
    plan = next(i for i in _connector(export_pdf="true").discover() if i.path.startswith("Plan"))
    assert plan.path == "Plan.pdf"
    assert plan.content_type == "application/pdf"


def test_fetch_dispatches_export_vs_download() -> None:
    connector = _connector()
    items = {i.path: i for i in connector.discover()}
    assert connector.fetch(items["notes.md"]) == b"hello"
    assert connector.fetch(items["Plan.docx"]) == b"<docx-bytes>"
    calls = connector._service.files().calls
    assert "get_media:f1" in calls
    assert f"export:d1:{_DOCX}" in calls
