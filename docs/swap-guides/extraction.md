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

**OCR / heavier rungs are optional extras** — install only what your ladder
names, so the image stays as light as your pipeline:

| Rung | Extra | For |
|---|---|---|
| `pdftables` | `[pdftables]` (pdfplumber, pure-Python) | born-digital PDFs where **table** fidelity matters — use *instead of* `pdf` in the ladder |
| `textract` | `[textract]` (Pillow; boto3 is base) | **AWS Textract OCR** (`DetectDocumentText`) — scanned PDFs/images, **handwriting** (managed, no local ML); fast/cheap, plain text |
| `textract_analyze` | `[textract]` (Pillow; boto3 is base) | **AWS Textract `AnalyzeDocument`** — structure-preserving: markdown **tables**, key-value **forms**, **figure markers**. `AFS_TEXTRACT_FEATURES=TABLES,LAYOUT,FORMS` (pricier than `textract`). Needs `textract:AnalyzeDocument` IAM |
| `tesseract` | `[tesseract]` (+ the tesseract binary) | lightweight self-hosted OCR — clean printed scans, no data leaves |
| `rapidocr` | `[rapidocr]` (onnxruntime+opencv) | PaddleOCR-quality OCR on ONNX (no torch) — better self-hosted recognition, still light |
| `docling` | `[docling]` (heavy ML) | born-digital PDFs with complex layout/tables |

```bash
pip install "afs-server[textract]"
# worker: light rungs first, then OCR/escalation for what they leave empty
export AFS_EXTRACTION_LADDER="text_native,pdf,docx,textract"
```

`textract` rasterizes PDF pages (pypdfium2) and OCRs each, or takes images
directly. More OCR engines (Tesseract, RapidOCR, PaddleOCR) follow the same
pattern; pick permissively-licensed ones — avoid AGPL (PyMuPDF) and
commercial-restricted (Surya/Marker) for bundled extras.

## Packaging the worker (only what your ladder uses)

The async extractor worker (`Dockerfile.worker`, ADR 0009) is **parametric**: the
rungs — and the system libraries they need — are a build arg, so you ship only
what you run. The default build is the lightweight, fully-capable set: `textract`
(AWS-managed OCR — scans, forms, handwriting — no local ML), giving a ~700 MB
image. Opt into heavier self-hosted rungs at build time:

```bash
# slim default (managed OCR): no torch, no OpenCV system libs
docker build -f Dockerfile.worker -t afs-worker .

# docling build: pulls torch + OpenCV (and its X11/GL libs) and pre-bakes the
# ML models. Keep the ladder in sync so the rung is actually used.
docker build -f Dockerfile.worker \
  --build-arg AFS_EXTRAS=textract,docling \
  --build-arg AFS_LADDER=text_native,pdf,docx,textract,docling \
  -t afs-worker-docling .
```

`AFS_EXTRAS` maps to the pyproject extras; the Dockerfile installs each extra's
system libs only when named (OpenCV/GL libs for `docling`/`rapidocr`; nothing for
the default). A rung named in the ladder whose extra isn't installed **declines**
at runtime (the ladder falls through; the doc lands `catalog_only`) rather than
crashing the worker — so a ladder/extras mismatch degrades safely. Match the
Terraform `extraction_ladder` (and bump `memory_mb`/`timeout_seconds`) to a
docling build when you deploy one.

Reference: `afs_server.extraction`, contract in `afs_core/contracts/normalize.py`,
decisions in [`0006`](../decisions/0006-extraction-normalizer-contract.md)
(contract) and [`0009`](../decisions/0009-async-extraction-pipeline.md) (sync vs async).
