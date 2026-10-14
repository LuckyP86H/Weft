"""Full-text search: ranking, snippets and limits, with no MCP involved."""

# pylint: disable=redefined-outer-name
# Test parameters deliberately reuse the fixture's name: that is how pytest
# injects fixtures. Pylint reads it as shadowing; it isn't.

import pytest

from weft.search import SNIPPET_MAX_CHARS, query_terms, score_text, search, snippet_for
from weft.vault import Vault


@pytest.fixture
def search_vault(vault_dir):
    """The shared fake vault plus a few notes with known term counts."""
    (vault_dir / "notes" / "crdt.md").write_text(
        "# CRDTs\n\nConflict-free replicated data types (CRDT).\nA CRDT merges without locks.\n"
    )
    (vault_dir / "inbox" / "mcp.md").write_text(
        "Deterministic MCP tools beat clever prompts.\nMCP over stdio.\n"
    )
    (vault_dir / "notes" / "both.md").write_text("CRDT notes for an MCP server.\n")
    (vault_dir / ".obsidian" / "hidden.md").write_text("crdt crdt crdt crdt")
    return Vault(vault_dir)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("CRDT", ["crdt"]),
        ("  mcp   CRDT ", ["mcp", "crdt"]),
        ("mcp MCP mcp", ["mcp"]),
        ("", []),
        ("   ", []),
    ],
)
def test_query_terms(query, expected):
    """Terms are lowercased, deduplicated and kept in query order."""
    assert query_terms(query) == expected


@pytest.mark.parametrize(
    ("text", "terms", "expected"),
    [
        ("CRDT crdt Crdt", ["crdt"], 3),
        ("CRDTs", ["crdt"], 1),
        ("mcp and crdt", ["mcp", "crdt"], 2),
        ("nothing here", ["crdt"], 0),
    ],
)
def test_score_text(text, terms, expected):
    """Score counts case-insensitive substring occurrences of every term."""
    assert score_text(text, terms) == expected


def test_ranks_by_score_then_path(search_vault):
    """More occurrences rank higher; ties fall back to path order."""
    hits = search(search_vault, "crdt mcp")
    assert [(h.path, h.score) for h in hits] == [
        ("notes/crdt.md", 3),
        ("inbox/mcp.md", 2),
        ("notes/both.md", 2),
    ]


def test_case_insensitive(search_vault):
    """Query case does not matter."""
    assert search(search_vault, "CrDt") == search(search_vault, "crdt")


def test_skips_obsidian_folder(search_vault):
    """Notes under .obsidian are never searched."""
    assert all(not h.path.startswith(".obsidian") for h in search(search_vault, "crdt"))


def test_no_match_returns_empty(search_vault):
    """A query that matches nothing returns no hits."""
    assert not search(search_vault, "kubernetes")


@pytest.mark.parametrize("query", ["", "   "])
def test_blank_query_returns_nothing(search_vault, query):
    """A blank query is not a request for every note."""
    assert not search(search_vault, query)


@pytest.mark.parametrize(("limit", "count"), [(1, 1), (2, 2), (10, 3), (0, 0)])
def test_limit(search_vault, limit, count):
    """At most ``limit`` hits come back, best first."""
    hits = search(search_vault, "crdt mcp", limit=limit)
    assert len(hits) == count
    if hits:
        assert hits[0].path == "notes/crdt.md"


def test_snippet_is_line_of_first_match_and_the_next(search_vault):
    """The snippet starts at the line of the earliest match."""
    [hit] = search(search_vault, "replicated")
    assert hit.snippet == (
        "Conflict-free replicated data types (CRDT).\nA CRDT merges without locks."
    )


@pytest.mark.parametrize(
    ("text", "terms", "expected"),
    [
        ("one\ntwo\nthree", ["two"], "two\nthree"),
        ("one\ntwo\nthree", ["three"], "three"),
        ("  indented match  \n\n", ["match"], "indented match"),
        ("zz first\nyy second", ["yy", "zz"], "zz first\nyy second"),
        ("no hit", ["absent"], ""),
    ],
)
def test_snippet_for(text, terms, expected):
    """Snippets start at the earliest match of any term, trimmed."""
    assert snippet_for(text, terms) == expected


def test_snippet_is_capped():
    """One huge line can't flood the agent's context."""
    snippet = snippet_for("match " + "x" * 1000, ["match"])
    assert len(snippet) == SNIPPET_MAX_CHARS
    assert snippet.endswith("…")


def test_badly_encoded_note_does_not_break_search(search_vault, vault_dir):
    """Undecodable bytes are replaced, not raised."""
    (vault_dir / "notes" / "latin1.md").write_bytes(b"caf\xe9 crdt\n")
    paths = [h.path for h in search(search_vault, "crdt")]
    assert "notes/latin1.md" in paths
