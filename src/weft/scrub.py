"""Layer 2 privacy: deterministic redaction of text before it is stored.

Pure functions only: no file I/O and no ``mcp`` import, so every rule is
testable with a plain string. Markers are visible on purpose (``[REDACTED:email]``)
so a reader can see that something was removed.

The report carries counts by category, never the matched text. Writing the
matched text into a report would make the report itself the leak.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

# Order matters: credentials run first so a token is never half-eaten by a
# later pattern (an email-looking fragment inside a key, for example).
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "credential",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
            r"|\bsk-[A-Za-z0-9_-]{8,}"
            r"|\bgh[pousr]_[A-Za-z0-9]{20,}"
            r"|\bxox[baprs]-[A-Za-z0-9-]{10,}"
            r"|\bAKIA[0-9A-Z]{16}\b"
            r"|(?i:\bbearer\s+)[A-Za-z0-9._~+/-]{8,}=*"
            r"|(?i:\bpassword\s*[:=]\s*)\S+"
            r"|(?i:\bapi[_-]?key\s*[:=]\s*)\S+"
        ),
    ),
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    (
        # 10+ digits with common separators. Dates (2026-10-14) and short
        # numbers do not match.
        "phone",
        re.compile(r"(?<![\w.])\+?\d{1,3}?[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{4}(?!\w)"),
    ),
)


@dataclass(frozen=True)
class Redaction:
    """How many matches one category removed."""

    category: str
    count: int


@dataclass(frozen=True)
class ScrubResult:
    """Scrubbed text plus a counts-only report."""

    scrubbed_text: str
    redactions: tuple[Redaction, ...]


def scrub(text: str, terms: Iterable[str] = ()) -> ScrubResult:
    """Replace sensitive spans in ``text`` with markers and count each category.

    ``terms`` are literal strings from the user's ``redact_terms`` setting
    (company names, codenames). They are matched case-insensitively, longest
    first, so a term that contains another term wins.
    """
    counts: Counter[str] = Counter()
    result = text

    for category, pattern in _RULES:
        result, n = pattern.subn(f"[REDACTED:{category}]", result)
        if n:
            counts[category] += n

    literal_terms = sorted({t for t in terms if t}, key=len, reverse=True)
    if literal_terms:
        term_pattern = re.compile("|".join(re.escape(t) for t in literal_terms), re.IGNORECASE)
        result, n = term_pattern.subn("[REDACTED:term]", result)
        if n:
            counts["term"] += n

    return ScrubResult(
        scrubbed_text=result,
        redactions=tuple(Redaction(category, n) for category, n in counts.items()),
    )
