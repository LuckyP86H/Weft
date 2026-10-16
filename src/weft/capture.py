"""Capture: scrub text and file it as a note in the vault inbox.

Plain Python with no ``mcp`` import. The clock is passed in, so tests can pin
the filename and ``created`` timestamp.

Everything that ends up on disk is scrubbed, not just the body: the filename
slug, the title and the source are derived from scrubbed text too. A slug built
from raw text would leak exactly what the body hides.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import get_args

from weft.scrub import Redaction, scrub
from weft.types import SourceType
from weft.vault import Vault

INBOX_DIR = "inbox"
SOURCE_TYPES: tuple[str, ...] = get_args(SourceType)
_SLUG_WORDS = 5
_SLUG_CJK_CHARS = 10
_TITLE_MAX = 80
_CJK_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]")


@dataclass(frozen=True)
class CaptureResult:
    """Where the note was filed and what was redacted on the way in."""

    note_path: str
    redactions: tuple[Redaction, ...]


def slugify(text: str, max_words: int = _SLUG_WORDS) -> str:
    """Hyphenated slug: up to ``_SLUG_CJK_CHARS`` CJK chars kept as-is, then
    up to ``max_words`` ASCII-folded lowercase words.

    Pure-English input behaves exactly as before; CJK input (which has no
    spaces to split into words) now contributes readable characters instead
    of collapsing to ``"note"``.
    """
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", folded.lower())
    cjk = "".join(_CJK_RE.findall(text))[:_SLUG_CJK_CHARS]
    parts = [cjk] if cjk else []
    parts.extend(words[:max_words])
    return "-".join(parts) or "note"


def _title(text: str) -> str:
    """One-line title: the first non-empty line, whitespace collapsed and capped."""
    for line in text.splitlines():
        line = " ".join(line.split())
        if line:
            return line[:_TITLE_MAX]
    return ""


def _yaml_str(value: str) -> str:
    """A double-quoted YAML scalar (JSON strings are valid YAML)."""
    return json.dumps(value, ensure_ascii=False)


def render_note(  # pylint: disable=too-many-arguments
    body: str,
    *,
    title: str,
    created: datetime,
    source_type: str,
    source: str | None,
    redactions: tuple[Redaction, ...],
) -> str:
    """Render a note: YAML frontmatter followed by the scrubbed body."""
    lines = [
        "---",
        f"title: {_yaml_str(title)}",
        f"created: {created.isoformat(timespec='seconds')}",
        f"source_type: {source_type}",
    ]
    if source:
        lines.append(f"source: {_yaml_str(source)}")
    lines += ["tags: []", "scrubbed: true"]
    if redactions:
        lines.append("redactions:")
        lines += [f'  - {{ category: "{r.category}", count: {r.count} }}' for r in redactions]
    else:
        lines.append("redactions: []")
    lines += ["---", "", body.rstrip("\n"), ""]
    return "\n".join(lines)


def capture(  # pylint: disable=too-many-arguments,too-many-locals
    vault: Vault,
    text: str,
    source_type: SourceType,
    *,
    now: datetime,
    source: str | None = None,
    title_hint: str | None = None,
    dry_run: bool = False,
) -> CaptureResult:
    """Scrub ``text`` and write it to ``<vault>/inbox/`` as a new note.

    Never overwrites: on a filename collision the vault appends ``-2``, ``-3``.
    With ``dry_run=True`` nothing is written; the returned ``note_path`` is
    the filename that *would* have been used.
    """
    if not text.strip():
        raise ValueError("text must not be empty")
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {', '.join(SOURCE_TYPES)}")

    counts: Counter[str] = Counter()

    def clean(raw: str) -> str:
        result = scrub(raw)
        for r in result.redactions:
            counts[r.category] += r.count
        return result.scrubbed_text

    body = clean(text)
    title = _title(clean(title_hint)) if title_hint else ""
    title = title or _title(body)
    clean_source = clean(source) if source else None

    redactions = tuple(Redaction(category, n) for category, n in counts.items())
    filename = f"{now:%Y-%m-%d-%H%M}-{slugify(title or body)}.md"
    content = render_note(
        body,
        title=title,
        created=now,
        source_type=source_type,
        source=clean_source,
        redactions=redactions,
    )
    path = vault.create_unique(INBOX_DIR, filename, content) if not dry_run else None
    return CaptureResult(
        note_path=path.relative_to(vault.root).as_posix()
        if path is not None
        else f"{INBOX_DIR}/{filename}",
        redactions=redactions,
    )
