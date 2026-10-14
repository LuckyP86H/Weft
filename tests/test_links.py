"""Link suggestions: tokenizing, overlap ranking and input rules, no MCP involved."""

# pylint: disable=redefined-outer-name
# Test parameters deliberately reuse the fixture's name: that is how pytest
# injects fixtures. Pylint reads it as shadowing; it isn't.

import pytest

from weft.links import (
    MAX_MATCHED_TERMS,
    NoteNotFoundError,
    strip_frontmatter,
    suggest_links,
    tokenize,
)
from weft.vault import PathEscapeError, Vault


@pytest.fixture
def links_vault(vault_dir):
    """The shared fake vault plus notes with known overlaps."""
    notes = vault_dir / "notes"
    (notes / "crdt.md").write_text("CRDTs replicate state across peers without locks.")
    (notes / "mcp.md").write_text("MCP tools are deterministic; the agent decides.")
    (notes / "sync.md").write_text("Peers sync state; replicate carefully.")
    (vault_dir / "inbox" / "draft.md").write_text(
        "---\ntitle: Draft\nscrubbed: true\n---\nHow do peers replicate state?\n"
    )
    return Vault(vault_dir)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CRDTs replicate State", {"crdts", "replicate", "state"}),
        ("the and with about", set()),
        ("an ox is ok", set()),
        ("snake_case words", {"snake", "case", "words"}),
        ("Café naïve", {"café", "naïve"}),
        ("v2 mcp2026 2026", {"mcp2026", "2026"}),
    ],
)
def test_tokenize(text, expected):
    """Lowercase, 3+ characters, stopwords dropped, underscores split."""
    assert tokenize(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---\ntitle: x\n---\nbody", "body"),
        ("---\ntitle: x\n---", ""),
        ("no frontmatter\n---\nkept", "no frontmatter\n---\nkept"),
        ("body\n---\ntitle: x\n---\n", "body\n---\ntitle: x\n---\n"),
    ],
)
def test_strip_frontmatter(text, expected):
    """Only a leading YAML block is metadata; later rules are content."""
    assert strip_frontmatter(text) == expected


def test_frontmatter_keys_do_not_count_as_shared_terms(links_vault):
    """'title' and 'scrubbed' appear in frontmatter only, so they never match."""
    hits = suggest_links(links_vault, text="title scrubbed")
    assert not hits


def test_ranks_by_shared_terms_then_title(links_vault):
    """More distinct shared terms rank higher; ties break by candidate."""
    hits = suggest_links(links_vault, text="peers replicate state")
    assert [(h.candidate, h.score) for h in hits] == [
        ("[[crdt]]", 3),
        ("[[draft]]", 3),
        ("[[sync]]", 3),
    ]


def test_score_counts_distinct_terms_not_repeats(links_vault):
    """Saying a word five times doesn't make a note five times as related."""
    [hit] = suggest_links(links_vault, text="deterministic deterministic deterministic")
    assert (hit.candidate, hit.score, hit.matched_terms) == ("[[mcp]]", 1, ["deterministic"])


def test_note_path_excludes_the_note_itself(links_vault):
    """A note is never suggested as a link to itself."""
    hits = suggest_links(links_vault, note_path="notes/crdt.md")
    candidates = [h.candidate for h in hits]
    assert "[[crdt]]" not in candidates
    assert candidates[:2] == ["[[draft]]", "[[sync]]"]


def test_matched_terms_are_sorted_and_capped(links_vault, vault_dir):
    """Matched terms are listed alphabetically, at most MAX_MATCHED_TERMS."""
    words = [f"term{i:02d}" for i in range(MAX_MATCHED_TERMS + 5)]
    (vault_dir / "notes" / "many.md").write_text(" ".join(words))
    [hit] = suggest_links(links_vault, text=" ".join(reversed(words)))
    assert hit.score == len(words)
    assert hit.matched_terms == words[:MAX_MATCHED_TERMS]


@pytest.mark.parametrize(("limit", "count"), [(1, 1), (2, 2), (10, 3), (0, 0)])
def test_limit(links_vault, limit, count):
    """At most ``limit`` candidates come back."""
    assert len(suggest_links(links_vault, text="peers replicate state", limit=limit)) == count


@pytest.mark.parametrize("text", ["", "the and of", "zzzz-unmatched"])
def test_nothing_to_match_returns_empty(links_vault, text):
    """No usable or shared terms means no suggestions."""
    assert not suggest_links(links_vault, text=text)


@pytest.mark.parametrize(
    "kwargs", [{}, {"note_path": "notes/crdt.md", "text": "both"}]
)
def test_exactly_one_input_required(links_vault, kwargs):
    """note_path and text are mutually exclusive, and one is required."""
    with pytest.raises(ValueError):
        suggest_links(links_vault, **kwargs)


@pytest.mark.parametrize("bad", ["missing.md", "notes", "../readme.txt"])
def test_note_path_must_be_an_existing_note(links_vault, bad):
    """note_path must name a markdown file that exists."""
    with pytest.raises((NoteNotFoundError, PathEscapeError)):
        suggest_links(links_vault, note_path=bad)


def test_note_path_cannot_escape_the_vault(links_vault):
    """The vault boundary applies to note_path too."""
    with pytest.raises(PathEscapeError):
        suggest_links(links_vault, note_path="../../etc/passwd")
