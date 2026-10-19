"""Full-text search over the vault's notes, ranked by term frequency.

Pure Python over ``Vault``: no MCP, no index, no network. Every call reads
the notes fresh, which is fine at personal-vault scale and means there is no
cache to go stale.

Ranking is deliberately simple and deterministic: a note's score is how many
times the query terms appear in it (case-insensitive), ties broken by path.
Deciding which hits matter is the agent's job.

Snippets are scrubbed before they leave the server. The vault may hold notes
that were never captured through Weft (a credentials cheatsheet, say), and a
snippet is text handed straight to the agent and on to its model provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from weft.scrub import scrub
from weft.vault import Vault

DEFAULT_LIMIT = 10
SNIPPET_MAX_CHARS = 240


@dataclass(frozen=True)
class SearchHit:
    """One matching note: where it is, a peek at the match, and its score."""

    path: str
    snippet: str
    score: int


def query_terms(query: str) -> list[str]:
    """Split a query into unique lowercase terms, keeping their order."""
    return list(dict.fromkeys(query.lower().split()))


def score_text(text: str, terms: list[str]) -> int:
    """Count how often ``terms`` occur in ``text`` (case-insensitive, substring)."""
    lowered = text.lower()
    return sum(lowered.count(term) for term in terms)


def snippet_for(text: str, terms: list[str]) -> str:
    """Return ~2 lines around the earliest match of any term.

    The line holding the first match plus the line after it, whitespace
    trimmed, scrubbed, and capped at ``SNIPPET_MAX_CHARS`` so one huge line
    can't flood the agent's context. Scrubbing runs before the cap, so a
    secret cut in half by the cap is still caught.
    """
    lowered = text.lower()
    positions = [i for i in (lowered.find(t) for t in terms) if i >= 0]
    if not positions:
        return ""
    lines = text.splitlines()
    line_no = text.count("\n", 0, min(positions))
    window = [line.strip() for line in lines[line_no : line_no + 2]]
    snippet = scrub("\n".join(line for line in window if line)).scrubbed_text
    if len(snippet) > SNIPPET_MAX_CHARS:
        snippet = snippet[: SNIPPET_MAX_CHARS - 1].rstrip() + "…"
    return snippet


def _read(path: Path) -> str:
    # errors="replace": one badly encoded note must not break the whole search.
    return path.read_text(encoding="utf-8", errors="replace")


def search(vault: Vault, query: str, limit: int = DEFAULT_LIMIT) -> list[SearchHit]:
    """Find notes containing any query term, best matches first.

    Returns at most ``limit`` hits with vault-relative POSIX paths. A blank
    query returns nothing rather than every note.
    """
    terms = query_terms(query)
    if not terms or limit < 1:
        return []
    hits = []
    for path in vault.iter_notes():
        text = _read(path)
        score = score_text(text, terms)
        if score:
            hits.append(
                SearchHit(
                    path=path.relative_to(vault.root).as_posix(),
                    snippet=snippet_for(text, terms),
                    score=score,
                )
            )
    hits.sort(key=lambda h: (-h.score, h.path))
    return hits[:limit]
