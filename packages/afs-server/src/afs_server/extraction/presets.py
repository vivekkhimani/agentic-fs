"""Pre-defined extraction pipelines users pick from instead of hand-listing rungs.

Set ``AFS_PIPELINE_PRESET=<name>`` for a curated ladder. Presets are intentionally
generic (by capability, not domain) and resolve to a list of rung names, so they
run on either engine — the Haystack default or the ``ladder`` lite mode. An
explicit ``AFS_EXTRACTION_LADDER`` always overrides a preset.
"""

from __future__ import annotations

# name -> ordered rungs (cheap first; later rungs escalate). Heavier rungs need
# their extra (textract / anthropic|openai); a named-but-uninstalled rung declines
# and the ladder falls through, so a preset never hard-fails on a missing extra.
PRESETS: dict[str, list[str]] = {
    # Lightweight, no extras — the slim inline default.
    "lite": ["text_native", "pdf", "docx"],
    # Add AWS-managed OCR so scans/handwriting are read (no local ML).
    "ocr": ["text_native", "pdf", "docx", "textract"],
    # Structure-preserving: pdfplumber + Textract AnalyzeDocument (tables/forms).
    "tables": ["text_native", "pdftables", "docx", "textract_analyze"],
    # Batteries-included multimodal — the llm rung also describes diagrams.
    "multimodal": ["text_native", "pdf", "docx", "llm"],
    # Everything, escalating light -> tables -> structured OCR -> LLM.
    "full": ["text_native", "pdftables", "docx", "textract_analyze", "llm"],
}


def preset_ladder(name: str) -> list[str]:
    """The rung list for a preset name. Raises ValueError on an unknown name."""
    try:
        return list(PRESETS[name])
    except KeyError:
        raise ValueError(
            f"unknown AFS_PIPELINE_PRESET {name!r}; available: {', '.join(sorted(PRESETS))}"
        ) from None
