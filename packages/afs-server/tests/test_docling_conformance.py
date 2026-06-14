"""Certifies the docling rung against the afs-core ``NormalizerConformance`` kit,
on a real multi-page PDF fixture.

Skipped unless the optional ``docling`` extra is installed (it pulls heavy ML
deps). Run it locally or in a dedicated CI lane with::

    uv run --extra docling pytest packages/afs-server/tests/test_docling_conformance.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("docling")

from afs_core.models import SourceDocument
from afs_core.testing import NormalizerConformance
from afs_server.extraction.docling import DoclingNormalizer

_FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


class TestDoclingNormalizer(NormalizerConformance):
    @pytest.fixture
    def normalizer(self) -> DoclingNormalizer:
        return DoclingNormalizer()

    @pytest.fixture
    def sample(self) -> SourceDocument:
        return SourceDocument(
            filename=_FIXTURE.name,
            content_type="application/pdf",
            size=_FIXTURE.stat().st_size,
            local_path=_FIXTURE,
        )
