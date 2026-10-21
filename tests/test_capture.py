"""Capture: filing scrubbed notes into the inbox, and the vault write it relies on."""

# pylint: disable=redefined-outer-name

from datetime import datetime, timezone

import pytest

from weft.capture import NoteMeta, capture, slugify
from weft.vault import PathEscapeError, Vault

NOW = datetime(2026, 10, 14, 6, 45, 30, tzinfo=timezone.utc)


@pytest.fixture
def vault(vault_dir):
    """A Vault over the shared fake vault."""
    return Vault(vault_dir)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Why MCP servers should be deterministic", "why-mcp-servers-should-be"),
        ("  Café  déjà-vu: naïve!! ", "cafe-deja-vu-naive"),
        ("", "note"),
        ("日本語だけ", "日本語だけ"),
        ("今天复盘了季度规划，明天要跟Jeffrey对齐", "今天复盘了季度规划明-jeffrey"),
        ("今天学了MCP", "今天学了-mcp"),
        ("[REDACTED:email] wrote", "redacted-email-wrote"),
        ("判断交给agent。Ping me", "判断交给-agent-ping-me"),
        ("ﬁle naïve", "file-naive"),
    ],
)
def test_slugify(text, expected):
    """Slugs are hyphenated: CJK chars kept as-is, then ASCII-folded words."""
    assert slugify(text) == expected


def test_capture_writes_note_with_frontmatter(vault, vault_dir):
    """A note lands in inbox/ with the filename and frontmatter from WEFT.md."""
    result = capture(
        vault,
        "Deterministic tools beat clever prompts.\nMore detail.",
        "article",
        now=NOW,
        source="https://example.com/mcp",
        title_hint="Why deterministic",
    )
    assert result.note_path == "inbox/2026-10-14-0645-why-deterministic.md"
    assert (vault_dir / result.note_path).read_text(encoding="utf-8") == (
        "---\n"
        'title: "Why deterministic"\n'
        "created: 2026-10-14T06:45:30+00:00\n"
        "source_type: article\n"
        'source: "https://example.com/mcp"\n'
        "tags: []\n"
        "scrubbed: true\n"
        "redactions: []\n"
        "---\n"
        "\n"
        "Deterministic tools beat clever prompts.\nMore detail.\n"
    )


def test_title_defaults_to_first_line_of_body(vault, vault_dir):
    """Without a title_hint the first non-empty line becomes the title."""
    result = capture(vault, "\n\nFirst real line\nsecond", "thought", now=NOW)
    assert result.note_path.endswith("-first-real-line.md")
    assert 'title: "First real line"' in (vault_dir / result.note_path).read_text()


def test_everything_written_is_scrubbed(vault, vault_dir):
    """Filename, title, source and body are all scrubbed, and counts add up."""
    result = capture(
        vault,
        "key sk-abc123XYZ and mail a@b.com",
        "work",
        now=NOW,
        source="https://x.com/?token=sk-secret123456",
        title_hint="Note for boss@corp.com",
    )
    written = (vault_dir / result.note_path).read_text(encoding="utf-8")
    for leaked in ("sk-abc123XYZ", "a@b.com", "boss@corp.com", "sk-secret123456"):
        assert leaked not in written
        assert leaked not in result.note_path
    assert {r.category: r.count for r in result.redactions} == {"credential": 2, "email": 2}
    assert '  - { category: "credential", count: 2 }' in written


def test_frontmatter_quotes_awkward_titles(vault, vault_dir):
    """Quotes and colons in a title cannot break the frontmatter."""
    result = capture(vault, "body", "thought", now=NOW, title_hint='He said "hi": ok')
    assert 'title: "He said \\"hi\\": ok"' in (vault_dir / result.note_path).read_text()


def test_capture_never_overwrites(vault, vault_dir):
    """Same minute, same title: later notes get -2, -3 and the first is intact."""
    paths = [
        capture(vault, f"body {i}", "thought", now=NOW, title_hint="Same").note_path
        for i in range(3)
    ]
    assert paths == [
        "inbox/2026-10-14-0645-same.md",
        "inbox/2026-10-14-0645-same-2.md",
        "inbox/2026-10-14-0645-same-3.md",
    ]
    assert "body 0" in (vault_dir / paths[0]).read_text()


def test_capture_into_a_configured_folder(vault, vault_dir):
    """inbox_dir picks the folder, created on demand; names with spaces are fine."""
    result = capture(vault, "a thought", "thought", now=NOW, inbox_dir="Inbox & Thoughts")
    assert result.note_path == "Inbox & Thoughts/2026-10-14-0645-a-thought.md"
    assert (vault_dir / "Inbox & Thoughts" / "2026-10-14-0645-a-thought.md").is_file()


def test_configured_folder_cannot_escape_the_vault(vault):
    """The vault boundary still applies, whatever the config says."""
    with pytest.raises(PathEscapeError):
        capture(vault, "a thought", "thought", now=NOW, inbox_dir="../outside")


def test_capture_creates_inbox_when_missing(vault, vault_dir):
    """The inbox folder is created on demand."""
    (vault_dir / "inbox" / "a.md").unlink()
    (vault_dir / "inbox").rmdir()
    capture(vault, "hello", "thought", now=NOW)
    assert (vault_dir / "inbox").is_dir()


def test_unknown_source_type_is_rejected_and_nothing_written(vault, vault_dir):
    """A bad source_type raises before anything touches the disk."""
    before = sorted(p.name for p in (vault_dir / "inbox").iterdir())
    with pytest.raises(ValueError, match="source_type"):
        capture(vault, "x", "gossip", now=NOW)  # type: ignore[arg-type]
    assert sorted(p.name for p in (vault_dir / "inbox").iterdir()) == before


@pytest.mark.parametrize("bad_text", ["", "   ", "\n\t \n"])
def test_empty_text_is_rejected_and_nothing_written(vault, vault_dir, bad_text):
    """Empty or whitespace-only text raises instead of filing a junk note."""
    before = sorted(p.name for p in (vault_dir / "inbox").iterdir())
    with pytest.raises(ValueError, match="text must not be empty"):
        capture(vault, bad_text, "thought", now=NOW)
    assert sorted(p.name for p in (vault_dir / "inbox").iterdir()) == before


def test_dry_run_writes_nothing_but_returns_would_be_path(vault, vault_dir):
    """dry_run computes the filename and redactions without touching disk."""
    before = sorted(p.name for p in (vault_dir / "inbox").iterdir())
    result = capture(
        vault, "mail me@acme.com", "thought", now=NOW, dry_run=True
    )
    assert sorted(p.name for p in (vault_dir / "inbox").iterdir()) == before
    assert result.note_path == "inbox/2026-10-14-0645-mail-redacted-email.md"
    assert [(r.category, r.count) for r in result.redactions] == [("email", 1)]


def test_dry_run_previews_the_collision_suffix(vault, vault_dir):
    """The preview names the file a real capture would create, suffix included."""
    first = capture(vault, "one", "thought", now=NOW, title_hint="Same")
    preview = capture(vault, "two", "thought", now=NOW, title_hint="Same", dry_run=True)
    real = capture(vault, "two", "thought", now=NOW, title_hint="Same")
    assert first.note_path == "inbox/2026-10-14-0645-same.md"
    assert preview.note_path == real.note_path == "inbox/2026-10-14-0645-same-2.md"
    assert "two" in (vault_dir / real.note_path).read_text()


def test_dry_run_does_not_create_a_missing_inbox(vault, vault_dir):
    """Previewing must not create the inbox folder."""
    (vault_dir / "inbox" / "a.md").unlink()
    (vault_dir / "inbox").rmdir()
    capture(vault, "hello", "thought", now=NOW, dry_run=True)
    assert not (vault_dir / "inbox").exists()


@pytest.mark.parametrize("bad", ["../escape.md", "sub/dir.md", "/abs.md"])
def test_create_unique_refuses_paths_in_filename(vault, bad):
    """A filename that contains a path is refused."""
    with pytest.raises(PathEscapeError):
        vault.create_unique("inbox", bad, "x")


def test_create_unique_refuses_directory_escape(vault):
    """A directory outside the vault is refused."""
    with pytest.raises(PathEscapeError):
        vault.create_unique("../outside", "n.md", "x")


def test_vault_fields_are_written_in_frontmatter(vault, vault_dir):
    """summary, domain, hub and tags land in the frontmatter, hub as a wikilink."""
    (vault_dir / "notes" / "Thought Stream.md").write_text("# hub")
    result = capture(
        vault,
        "Deterministic tools beat clever prompts.",
        "thought",
        now=NOW,
        meta=NoteMeta(
            note_type="reflection",
            summary="  Tools should be deterministic.\nignored second line",
            domain="Backend Engineering",
            hub="[[Thought Stream]]",
            tags=("#inbox/thoughts", "mcp", "mcp", " "),
        ),
    )
    written = (vault_dir / result.note_path).read_text(encoding="utf-8")
    assert written.startswith(
        "---\n"
        'title: "Deterministic tools beat clever prompts."\n'
        "created: 2026-10-14T06:45:30+00:00\n"
        "source_type: thought\n"
        'type: "reflection"\n'
        'domain: "Backend Engineering"\n'
        'hub: "[[Thought Stream]]"\n'
        'summary: "Tools should be deterministic."\n'
        "tags:\n"
        '  - "inbox/thoughts"\n'
        '  - "mcp"\n'
        "scrubbed: true\n"
    )


def test_vault_fields_are_scrubbed(vault, vault_dir):
    """A secret in a summary, domain or tag is redacted and counted."""
    result = capture(
        vault,
        "body",
        "work",
        now=NOW,
        meta=NoteMeta(summary="ask boss@corp.com", domain="sk-abc123XYZ99", tags=("a@b.com",)),
    )
    written = (vault_dir / result.note_path).read_text(encoding="utf-8")
    for leaked in ("boss@corp.com", "sk-abc123XYZ99", "a@b.com"):
        assert leaked not in written
    assert {r.category: r.count for r in result.redactions} == {"email": 2, "credential": 1}


@pytest.mark.parametrize(
    ("hub", "written"),
    [("b", 'hub: "[[b]]"'), ("[[b]]", 'hub: "[[b]]"'), ("[[b|Bee]]", 'hub: "[[b]]"')],
)
def test_hub_accepts_names_and_wikilinks(vault, vault_dir, hub, written):
    """A hub can be given bare or as a wikilink; it is written as [[name]]."""
    result = capture(vault, "body", "thought", now=NOW, meta=NoteMeta(hub=hub))
    assert written in (vault_dir / result.note_path).read_text(encoding="utf-8")


@pytest.mark.parametrize("dry_run", [False, True])
def test_unknown_hub_is_refused_before_writing(vault, vault_dir, dry_run):
    """A hub that is not an existing note fails, and nothing is written."""
    before = sorted(p.name for p in (vault_dir / "inbox").iterdir())
    with pytest.raises(ValueError, match="existing note"):
        capture(vault, "body", "thought", now=NOW, meta=NoteMeta(hub="Nope"), dry_run=dry_run)
    assert sorted(p.name for p in (vault_dir / "inbox").iterdir()) == before


def test_tags_with_spaces_are_refused(vault):
    """Obsidian tags cannot contain spaces, so the call fails instead of guessing."""
    with pytest.raises(ValueError, match="spaces"):
        capture(vault, "body", "thought", now=NOW, meta=NoteMeta(tags=("two words",)))
