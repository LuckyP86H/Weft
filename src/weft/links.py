"""Link suggestions: which existing notes share the most words with this one?

Pure Python over ``Vault``. The server ranks; it never inserts a link.
Choosing which candidates are real connections is a judgment call, so it
stays with the agent (and you).

Scoring is weighted token overlap: tokenize both sides (lowercase words of
3+ characters, minus stopwords and YAML frontmatter), and a candidate's score
is the sum of the shared terms' rarity across the vault (BM25's inverse
document frequency, the same idea Elasticsearch ranks with). A word every note
shares, like a navigation bar or a footer heading, adds almost nothing; a word
only two notes share adds a lot. Ties break by candidate (the ``[[stem]]``
string), so the same vault always gives the same answer.

Notes the input already links to (``[[Note]]`` anywhere, frontmatter
included) are skipped: suggesting them again tells the agent nothing.

Chinese and Japanese have no spaces between words, so a CJK run is split into
overlapping two-character terms (知识管理 -> 知识, 识管, 管理), the usual
dictionary-free approach.

Both sides are scrubbed before tokenizing, because ``matched_terms`` goes back
to the agent: without it, two notes that mention ``bob@acme.com`` would return
``bob``, ``acme`` and ``com``. The resulting markers like ``[REDACTED:email]``
are then dropped: every scrubbed note has them, so they say nothing about topic.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from weft.scrub import scrub
from weft.vault import Vault, VaultError

DEFAULT_LIMIT = 10
MAX_MATCHED_TERMS = 10

_CJK = "\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff"
_WORD = re.compile(rf"[^\W_{_CJK}]{{3,}}")
_CJK_RUN = re.compile(rf"[{_CJK}]+")
_REDACTION_MARKER = re.compile(r"\[REDACTED:\w+\]")
# [[Note]], [[folder/Note|alias]], [[Note#heading]]: the target is the part
# before |, # or ^, and Obsidian matches it by file name.
_WIKILINK = re.compile(r"\[\[([^\]|#^]+)")
_FRONTMATTER = re.compile(r"\A---\n.*?\n---[ \t]*(?:\n|\Z)", re.DOTALL)

# Common English words that would make every note look related to every other.
STOPWORDS = frozenset(
    """
    about above after again against all also and any are aren because been
    before being below between both but can cannot could did didn does doesn
    doing don down during each few for from further had hadn has hasn have
    haven having her here hers herself him himself his how into isn its itself
    just let more most mustn myself nor not now off once only other our ours
    ourselves out over own same she should shouldn some such than that the
    their theirs them themselves then there these they this those through too
    under until very was wasn were weren what when where which while who whom
    why will with won would wouldn you your yours yourself yourselves
    """.split()
)


# Particles and pronouns that glue Chinese sentences together; a bigram that
# contains one (的核, 我们) is grammar, not topic.
CJK_STOPCHARS = frozenset("的了是在和与及之也就都而我你他她它们这那个一不有")


class NoteNotFoundError(VaultError):
    """``note_path`` does not name a markdown note inside the vault."""


@dataclass(frozen=True)
class LinkSuggestion:
    """One candidate note to link to, with why it was suggested."""

    candidate: str
    score: float
    matched_terms: list[str] = field(default_factory=list)


def strip_frontmatter(text: str) -> str:
    """Drop a leading YAML frontmatter block, which is metadata, not content."""
    return _FRONTMATTER.sub("", text, count=1)


def _cjk_bigrams(run: str) -> set[str]:
    """Overlapping two-character terms of a CJK run, minus grammar bigrams."""
    pairs = (run[i : i + 2] for i in range(len(run) - 1))
    return {p for p in pairs if not CJK_STOPCHARS.intersection(p)}


def tokenize(text: str) -> set[str]:
    """Distinct terms: lowercase words of 3+ letters/digits (stopwords removed)
    plus CJK bigrams. Sensitive spans are scrubbed first, so no term can be a
    piece of a secret; frontmatter and scrubber markers are ignored."""
    body = scrub(strip_frontmatter(text)).scrubbed_text
    body = _REDACTION_MARKER.sub(" ", body).casefold()
    terms = {w for w in _WORD.findall(body) if w not in STOPWORDS}
    for run in _CJK_RUN.findall(body):
        terms |= _cjk_bigrams(run)
    return terms


def linked_notes(text: str) -> set[str]:
    """File names (without ``.md``) that ``text`` already links to."""
    return {Path(target.strip()).stem for target in _WIKILINK.findall(text)}


def idf(doc_freq: int, n_docs: int) -> float:
    """BM25 inverse document frequency: how much one shared term is worth.

    Near zero for a term in every note, high for a rare one. The ``+ 1``
    keeps it positive, so even a two-note vault can rank.
    """
    return math.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1)


def suggest_links(
    vault: Vault,
    *,
    note_path: str | None = None,
    text: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[LinkSuggestion]:
    """Rank existing notes by the rarity-weighted terms they share with the input.

    Give exactly one of ``note_path`` (vault-relative; that note is excluded
    from its own suggestions) or ``text``. Candidates are ``[[stem]]``
    wikilinks, since Obsidian resolves links by file name.
    """
    if (note_path is None) == (text is None):
        raise ValueError("Give exactly one of note_path or text.")
    source = None
    if note_path is not None:
        source = vault.resolve(note_path)
        if source.suffix != ".md" or not source.is_file():
            raise NoteNotFoundError(f"No markdown note at: {note_path}")
        text = source.read_text(encoding="utf-8", errors="replace")
    text = text or ""
    terms = tokenize(text)
    if not terms or limit < 1:
        return []

    # Read every note once: document frequencies need the whole vault.
    # Not cached yet: this re-reads, re-scrubs and re-tokenizes every call.
    # Fine at hundreds of notes; if it gets slow, cache terms by (path, mtime).
    notes = {
        path: tokenize(path.read_text(encoding="utf-8", errors="replace"))
        for path in vault.iter_notes()
    }
    doc_freq = {t: sum(t in note_terms for note_terms in notes.values()) for t in terms}
    weight = {t: idf(doc_freq[t], len(notes)) for t in terms}
    already_linked = linked_notes(text)

    suggestions = []
    for path, note_terms in notes.items():
        if path == source or path.stem in already_linked:
            continue
        if shared := terms & note_terms:
            ranked = sorted(shared, key=lambda t: (-weight[t], t))
            suggestions.append(
                LinkSuggestion(
                    candidate=f"[[{path.stem}]]",
                    score=round(sum(weight[t] for t in shared), 3),
                    matched_terms=ranked[:MAX_MATCHED_TERMS],
                )
            )
    suggestions.sort(key=lambda s: (-s.score, s.candidate))
    return suggestions[:limit]
