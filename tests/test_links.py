"""Link suggestions: tokenizing, overlap ranking and input rules, no MCP involved."""

# pylint: disable=redefined-outer-name
# Test parameters deliberately reuse the fixture's name: that is how pytest
# injects fixtures. Pylint reads it as shadowing; it isn't.

import pytest

from weft.links import (
    MAX_MATCHED_TERMS,
    NoteNotFoundError,
    idf,
    linked_notes,
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
        ("key [REDACTED:credential] sent", {"key", "sent"}),
        ("mail bob@acme.com today", {"mail", "today"}),
        ("知识管理", {"知识", "识管", "管理"}),
        ("我们的笔记", {"笔记"}),
        ("MCP服务器", {"mcp", "服务", "务器"}),
        ("书", set()),
    ],
)
def test_tokenize(text, expected):
    """Lowercase, 3+ characters, stopwords dropped, underscores split, CJK as
    bigrams minus grammar characters, scrubber markers ignored."""
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


def test_redaction_markers_alone_do_not_link_notes(links_vault, vault_dir):
    """Two scrubbed notes are not related just because both had an email removed."""
    (vault_dir / "notes" / "lunch.md").write_text("Lunch with [REDACTED:email]")
    assert not suggest_links(links_vault, text="Ping [REDACTED:email] tomorrow")


def test_matched_terms_never_leak_pieces_of_a_secret(links_vault, vault_dir):
    """A note that still holds raw PII (written outside Weft) must not hand its
    pieces back to the agent: the email links nothing, only real words do."""
    (vault_dir / "notes" / "falcon.md").write_text("Falcon kickoff, email bob@acme.com")
    [hit] = suggest_links(links_vault, text="email bob@acme.com re Falcon")
    assert hit.candidate == "[[falcon]]"
    assert set(hit.matched_terms) == {"falcon", "email"}
    assert not suggest_links(links_vault, text="bob@acme.com")


def test_chinese_notes_link_by_shared_bigrams(links_vault, vault_dir):
    """Chinese has no spaces; shared two-character terms still connect notes."""
    (vault_dir / "notes" / "zettel.md").write_text("知识管理的核心是笔记之间的链接")
    [hit] = suggest_links(links_vault, text="今天讨论了知识管理和笔记系统")
    assert hit.candidate == "[[zettel]]"
    assert hit.matched_terms == ["知识", "笔记", "管理", "识管"]


def test_ranks_by_shared_terms_then_candidate(links_vault):
    """Equal shared terms give equal scores; ties break by candidate."""
    hits = suggest_links(links_vault, text="peers replicate state")
    three_of_seven = round(3 * idf(3, 7), 3)
    assert [(h.candidate, h.score) for h in hits] == [
        ("[[crdt]]", three_of_seven),
        ("[[draft]]", three_of_seven),
        ("[[sync]]", three_of_seven),
    ]


def test_score_counts_distinct_terms_not_repeats(links_vault):
    """Saying a word five times doesn't make a note five times as related."""
    [hit] = suggest_links(links_vault, text="deterministic deterministic deterministic")
    assert (hit.candidate, hit.score, hit.matched_terms) == (
        "[[mcp]]",
        round(idf(1, 7), 3),
        ["deterministic"],
    )


@pytest.mark.parametrize(("doc_freq", "n_docs"), [(1, 2), (2, 2), (1, 30), (30, 30)])
def test_idf_is_positive_and_falls_as_terms_get_common(doc_freq, n_docs):
    """Rarer terms are worth more, and nothing is ever worth zero or less."""
    assert 0 < idf(doc_freq, n_docs)
    if doc_freq > 1:
        assert idf(doc_freq, n_docs) < idf(doc_freq - 1, n_docs)


def test_boilerplate_every_note_shares_does_not_outrank_a_real_topic(tmp_path):
    """A navigation bar on every note must not beat one shared rare word."""
    nav = "Navigation: Dashboard Backend Engineering Hub Faith Formation Hub\n"
    for i in range(6):
        (tmp_path / f"filler{i}.md").write_text(nav + f"unrelated topic{i}")
    (tmp_path / "celery.md").write_text(nav + "Celery retries with exponential backoff.")
    hits = suggest_links(Vault(tmp_path), text=nav + "How does backoff work?")
    assert hits[0].candidate == "[[celery]]"
    assert hits[0].matched_terms[0] == "backoff"
    assert hits[0].score > 3 * hits[1].score


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("see [[crdt]] and [[notes/sync|Sync]]", {"crdt", "sync"}),
        ('---\nhub: "[[mcp]]"\n---\nbody [[Draft#Heading]]', {"mcp", "Draft"}),
        ("no links here", set()),
    ],
)
def test_linked_notes(text, expected):
    """Link targets by file name: alias, heading and folder parts dropped."""
    assert linked_notes(text) == expected


def test_already_linked_notes_are_skipped(links_vault):
    """A note the input already links to is not suggested again."""
    hits = suggest_links(links_vault, text="[[crdt]] peers replicate state")
    assert [h.candidate for h in hits] == ["[[draft]]", "[[sync]]"]


def test_note_path_excludes_the_note_itself(links_vault):
    """A note is never suggested as a link to itself."""
    hits = suggest_links(links_vault, note_path="notes/crdt.md")
    candidates = [h.candidate for h in hits]
    assert "[[crdt]]" not in candidates
    assert candidates[:2] == ["[[draft]]", "[[sync]]"]


def test_matched_terms_are_sorted_and_capped(links_vault, vault_dir):
    """Equally rare matched terms are listed alphabetically, at most MAX_MATCHED_TERMS."""
    words = [f"term{i:02d}" for i in range(MAX_MATCHED_TERMS + 5)]
    (vault_dir / "notes" / "many.md").write_text(" ".join(words))
    [hit] = suggest_links(links_vault, text=" ".join(reversed(words)))
    assert hit.score == round(len(words) * idf(1, 8), 3)
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
