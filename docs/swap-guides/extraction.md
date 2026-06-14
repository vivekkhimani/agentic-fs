# Swap guide: extraction (bring your own parser)

Extraction is how a raw document becomes readable text. It's a pluggable contract
— `afs_core.contracts.Normalizer` — so you can add a parser for any format
(better PDF parsing, OCR, a proprietary file type) without forking.

A normalizer's only job is **bytes → per-page markdown**. It never touches S3
keys or catalog rows — the pipeline handles all of that.

## The contract

```python
class Normalizer(Protocol):
    name: str
    def accepts(self, doc: SourceDocument) -> bool          # "I can parse this MIME/ext"
    async def normalize(self, doc: SourceDocument) -> NormalizedDocument   # or raise NormalizationError(reason)
```
- `SourceDocument` gives you `filename`, `content_type`, `size`, and `local_path`
  (the original staged to disk — stream from it; don't hold bytes).
- `NormalizedDocument` is `pages: list[PageText]` (1-based markdown + an optional
  `source_locator` like `"pdf:page=12"`) + a `QualityReport` (drives escalation).

## Write one

1. **Implement** the `Normalizer` Protocol (e.g. wrap Docling, Tika, or a SaaS
   parser).
2. **Certify** it — subclass the kit and make it green:
   ```python
   from afs_core.testing import NormalizerConformance

   class TestMyParser(NormalizerConformance):
       @pytest.fixture
       def normalizer(self): return MyParser()
       @pytest.fixture
       def sample(self, tmp_path): ...   # a SourceDocument your parser accepts
   ```
3. **Register** an entry point whose value is a zero-arg factory:
   ```toml
   [project.entry-points."afs.normalizers"]
   myparser = "mypkg.parser:MyParser"
   ```
4. **Add it to the ladder** — name it (before/after the builtins) so the
   `ExtractionPipeline` tries it in order. A doc that no rung can read lands
   `catalog_only` (listed + citeable, never silently dropped).

## How the ladder + quality gate work

The pipeline walks the ladder in order; the first normalizer that `accepts` the
document and produces an above-quality-gate result wins. A low-quality result
(e.g. a text-layer-less scanned PDF) falls through to the next rung — this is how
the lightweight rungs handle the common case and **`docling` escalates** for what
they can't (scans, complex tables/layout).

**Lightweight builtins (always on, no ML):** `text_native`, `pdf` (pypdfium2 text
layer), `docx` (python-docx). Common files extract **synchronously, in-request** —
the default ladder is `text_native,pdf,docx`.

**`docling`** (PDF/Office/images, OCR) is a heavier **optional extra**, for the
quality cases — put it on the async extractor worker, not the request path:

```bash
pip install "afs-server[docling]"
# worker: try the light rungs first, escalate to docling where they fall short
export AFS_EXTRACTION_LADDER="text_native,pdf,docx,docling"
```

Reference: `afs_server.extraction`, contract in `afs_core/contracts/normalize.py`,
decisions in [`0006`](../decisions/0006-extraction-normalizer-contract.md)
(contract) and [`0009`](../decisions/0009-async-extraction-pipeline.md) (sync vs async).
