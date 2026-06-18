"""Regex engine seam for the read path (ADR 0015, Phase 2).

Untrusted agent/user patterns reach ``fs_grep``, so the engine must be
**linear-time** — RE2 (``google-re2``) has no catastrophic backtracking, closing
the ReDoS hole that stdlib ``re`` leaves open (``(a+)+$`` can pin a CPU under
``re``; RE2 runs it in microseconds). RE2's dialect drops lookaround/backreferences;
those surface as a clean ``PatternError`` (→ ``ValidationError`` at the service).

``re`` is kept only as a fallback when the RE2 wheel is unavailable on an exotic
platform — it trades the safety guarantee for availability, logged once so the
degradation is visible. One compile point, so callers never branch on the engine.
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)

try:  # RE2 is a base dependency; the fallback is for platforms without a wheel.
    import re2 as _re2

    _HAVE_RE2 = True
except ImportError:  # pragma: no cover - exercised only where the wheel is absent
    _re2 = None
    _HAVE_RE2 = False
    logger.warning(
        "google-re2 unavailable; falling back to stdlib re for grep "
        "(patterns are no longer guaranteed linear-time)"
    )


class PatternError(Exception):
    """A pattern that doesn't compile, or uses a construct the engine rejects."""


class Matcher:
    """Engine-agnostic wrapper. Both RE2 and ``re`` compiled patterns expose
    ``search``/``finditer`` with ``.start()`` on matches, so one wrapper covers both."""

    __slots__ = ("_prog",)

    def __init__(self, prog: object) -> None:
        self._prog = prog

    def search(self, s: str) -> bool:
        """True if the pattern matches anywhere in ``s``."""
        return self._prog.search(s) is not None  # type: ignore[attr-defined]

    def match_starts(self, s: str) -> list[int]:
        """Start offsets of all non-overlapping matches in ``s`` (for multiline mode)."""
        return [m.start() for m in self._prog.finditer(s)]  # type: ignore[attr-defined]


def compile_pattern(pattern: str, *, ignore_case: bool, multiline: bool = False) -> Matcher:
    """Compile ``pattern`` with the safe engine if present, else stdlib ``re``.

    ``multiline`` lets ``.`` span newlines (Python ``re.DOTALL`` / RE2 ``dot_nl``) so
    a pattern can match across lines within a page. Raises ``PatternError`` on a bad
    or unsupported pattern.
    """
    if _HAVE_RE2:
        opts = _re2.Options()
        opts.log_errors = False
        opts.case_sensitive = not ignore_case
        if multiline:
            opts.dot_nl = True  # '.' matches newline — patterns can span lines
            opts.one_line = False  # '^'/'$' at line boundaries where supported
        try:
            return Matcher(_re2.compile(pattern, opts))
        except _re2.error as err:
            msg = err.args[0] if err.args else str(err)
            if isinstance(msg, bytes):
                msg = msg.decode("utf-8", "replace")
            raise PatternError(str(msg)) from err

    flags = 0
    if ignore_case:
        flags |= re.IGNORECASE
    if multiline:
        flags |= re.DOTALL | re.MULTILINE
    try:
        return Matcher(re.compile(pattern, flags))
    except re.error as err:
        raise PatternError(str(err)) from err
