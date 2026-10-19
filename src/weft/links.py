"""Link suggestions: which existing notes share the most words with this one?

Pure Python over ``Vault``. The server ranks; it never inserts a link.
Choosing which candidates are real connections is a judgment call, so it
stays with the agent (and you).

Scoring is plain token overlap: tokenize both sides (lowercase words of 3+
characters, minus stopwords and YAML frontmatter), and a candidate's score is
how many distinct terms it shares with the input. Ties break by title, so the
same vault always gives the same answer.

Chinese and Japanese have no spaces between words, so a CJK run is split into
overlapping two-character terms (知识管理 -> 知识, 识管, 管理), the usual
dictionary-free approach. Scrubber markers like ``[REDACTED:email]`` are
dropped first: every scrubbed note has them, so they say nothing about topic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from weft.vault import Vault, VaultError

DEFAULT_LIMIT = 10
MAX_MATCHED_TERMS = 10

_CJK = "\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff"
_WORD = re.compile(rf"[^\W_{_CJK}]{{3,}}")
_CJK_RUN = re.compile(rf"[{_CJK}]+")
_REDACTION_MARKER = re.compile(r"\[REDACTED:\w+\]")
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
    score: int
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
    plus CJK bigrams. Frontmatter and scrubber markers are ignored."""
    body = _REDACTION_MARKER.sub(" ", strip_frontmatter(text)).casefold()
    terms = {w for w in _WORD.findall(body) if w not in STOPWORDS}
    for run in _CJK_RUN.findall(body):
        terms |= _cjk_bigrams(run)
    return terms


def suggest_links(
    vault: Vault,
    *,
    note_path: str | None = None,
    text: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[LinkSuggestion]:
    """Rank existing notes by how many terms they share with the input.

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
    terms = tokenize(text or "")
    if not terms or limit < 1:
        return []

    suggestions = []
    for path in vault.iter_notes():
        if path == source:
            continue
        shared = terms & tokenize(path.read_text(encoding="utf-8", errors="replace"))
        if shared:
            suggestions.append(
                LinkSuggestion(
                    candidate=f"[[{path.stem}]]",
                    score=len(shared),
                    matched_terms=sorted(shared)[:MAX_MATCHED_TERMS],
                )
            )
    suggestions.sort(key=lambda s: (-s.score, s.candidate))
    return suggestions[:limit]
