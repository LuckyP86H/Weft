"""The MCP layer, exercised through a real MCP client (in memory, no subprocess)."""

# pylint: disable=redefined-outer-name
# Test parameters deliberately reuse the fixture's name: that is how pytest
# injects fixtures. Pylint reads it as shadowing; it isn't.

import re

import pytest
from mcp import Client

from weft.server import build_server
from weft.vault import Vault


@pytest.fixture
def mcp_client(vault_dir):
    """An in-memory MCP client bound to a temp vault."""
    return Client(build_server(Vault(vault_dir)))


async def test_lists_registered_tools(mcp_client):
    """The server exposes exactly the v0.1 tools registered so far."""
    async with mcp_client:
        tools = await mcp_client.list_tools()
    assert sorted(t.name for t in tools.tools) == [
        "weft_capture",
        "weft_scrub",
        "weft_search",
        "weft_vault_info",
    ]


async def test_capture_tool_declares_write_annotations(mcp_client):
    """weft_capture is annotated as a non-destructive write, not read-only."""
    async with mcp_client:
        tools = await mcp_client.list_tools()
    capture_tool = next(t for t in tools.tools if t.name == "weft_capture")
    assert capture_tool.annotations is not None
    assert capture_tool.annotations.read_only_hint is False
    assert capture_tool.annotations.destructive_hint is False
    assert capture_tool.annotations.idempotent_hint is False


async def test_vault_info_reports_the_injected_vault(mcp_client, vault_dir):
    """weft_vault_info reports the vault the server was built with."""
    async with mcp_client:
        result = await mcp_client.call_tool("weft_vault_info", {})
    assert result.structured_content == {
        "root": str(vault_dir.resolve()),
        "is_obsidian_vault": True,
        "note_count": 3,
        "conventions_file": None,
    }


async def test_vault_without_agents_md_has_no_conventions(mcp_client):
    """No AGENTS.md: no resource, and the instructions don't mention one."""
    async with mcp_client:
        resources = await mcp_client.list_resources()
        assert resources.resources == []
        assert "weft://conventions" not in (mcp_client.instructions or "")


async def test_agents_md_is_offered_as_a_scrubbed_resource(vault_dir):
    """AGENTS.md is listed, read fresh, scrubbed, and pointed to by the instructions."""
    agents = vault_dir / "AGENTS.md"
    agents.write_text("# Rules\nhub: [[Dashboard]]\nowner: me@acme.com\n")
    async with Client(build_server(Vault(vault_dir))) as client:
        resources = await client.list_resources()
        assert [str(r.uri) for r in resources.resources] == ["weft://conventions"]
        assert "weft://conventions" in client.instructions
        agents.write_text("# Rules v2\nowner: me@acme.com\n")
        result = await client.read_resource("weft://conventions")
        info = await client.call_tool("weft_vault_info", {})
    [content] = result.contents
    assert content.text == "# Rules v2\nowner: [REDACTED:email]\n"
    assert content.mime_type == "text/markdown"
    assert info.structured_content["conventions_file"] == "AGENTS.md"


async def test_scrub_tool_redacts_and_reports_counts(mcp_client):
    """weft_scrub returns scrubbed text and a counts-only report over MCP."""
    async with mcp_client:
        result = await mcp_client.call_tool(
            "weft_scrub", {"text": "key sk-abc123XYZ, mail me@acme.com"}
        )
    assert result.structured_content == {
        "scrubbed_text": "key [REDACTED:credential], mail [REDACTED:email]",
        "redactions": [
            {"category": "credential", "count": 1},
            {"category": "email", "count": 1},
        ],
    }


async def test_capture_tool_files_a_scrubbed_note(mcp_client, vault_dir):
    """weft_capture writes a scrubbed note into the inbox and reports counts."""
    async with mcp_client:
        result = await mcp_client.call_tool(
            "weft_capture",
            {"text": "mail me@acme.com about the plan", "source_type": "thought"},
        )
    data = result.structured_content
    assert data["redactions"] == [{"category": "email", "count": 1}]
    assert re.fullmatch(
        r"inbox/\d{4}-\d{2}-\d{2}-\d{4}-mail-redacted-email-about-the\.md",
        data["note_path"],
    )
    written = (vault_dir / data["note_path"]).read_text(encoding="utf-8")
    assert "me@acme.com" not in written
    assert "[REDACTED:email]" in written


async def test_capture_tool_writes_vault_fields(mcp_client, vault_dir):
    """summary, domain, hub and tags pass through MCP into the frontmatter."""
    async with mcp_client:
        result = await mcp_client.call_tool(
            "weft_capture",
            {
                "text": "a thought",
                "source_type": "thought",
                "note_type": "reflection",
                "summary": "One line.",
                "domain": "Thought Stream",
                "hub": "top",
                "tags": ["inbox/thoughts"],
            },
        )
    assert not result.is_error
    written = (vault_dir / result.structured_content["note_path"]).read_text(encoding="utf-8")
    assert 'type: "reflection"' in written
    assert 'hub: "[[top]]"' in written
    assert 'summary: "One line."' in written
    assert '  - "inbox/thoughts"' in written


async def test_capture_tool_explains_an_unknown_hub(mcp_client):
    """A hub that does not exist comes back as a readable tool error."""
    async with mcp_client:
        result = await mcp_client.call_tool(
            "weft_capture", {"text": "x", "source_type": "thought", "hub": "Nope"}
        )
    assert result.is_error
    assert "existing note" in result.content[0].text


async def test_capture_tool_rejects_unknown_source_type(mcp_client, vault_dir):
    """An unknown source_type is rejected before any file is written."""
    before = sorted(p.name for p in (vault_dir / "inbox").iterdir())
    async with mcp_client:
        result = await mcp_client.call_tool(
            "weft_capture", {"text": "x", "source_type": "gossip"}
        )
    assert result.is_error
    assert sorted(p.name for p in (vault_dir / "inbox").iterdir()) == before


async def test_capture_tool_returns_human_readable_summary(mcp_client):
    """The text content is a one-line summary, not raw JSON."""
    async with mcp_client:
        result = await mcp_client.call_tool(
            "weft_capture",
            {"text": "mail me@acme.com", "source_type": "thought"},
        )
    assert not result.is_error
    text = result.content[0].text
    assert text.startswith("Captured to inbox/")
    assert "redacted: email x 1" in text
    # The machine-readable side is still there too.
    assert result.structured_content["dry_run"] is False
    assert result.structured_content["redactions"] == [
        {"category": "email", "count": 1}
    ]


async def test_capture_tool_dry_run_writes_nothing(mcp_client, vault_dir):
    """dry_run previews the filename without touching the inbox."""
    before = sorted(p.name for p in (vault_dir / "inbox").iterdir())
    async with mcp_client:
        result = await mcp_client.call_tool(
            "weft_capture",
            {"text": "mail me@acme.com", "source_type": "thought", "dry_run": True},
        )
    assert not result.is_error
    assert sorted(p.name for p in (vault_dir / "inbox").iterdir()) == before
    assert result.content[0].text.startswith("[dry run] would capture to inbox/")
    assert result.structured_content["dry_run"] is True


async def test_capture_tool_rejects_empty_text(mcp_client, vault_dir):
    """Empty text is rejected before any file is written."""
    before = sorted(p.name for p in (vault_dir / "inbox").iterdir())
    async with mcp_client:
        result = await mcp_client.call_tool(
            "weft_capture", {"text": "   ", "source_type": "thought"}
        )
    assert result.is_error
    # The agent must be told why, not just "Error executing tool".
    assert "text must not be empty" in result.content[0].text
    assert sorted(p.name for p in (vault_dir / "inbox").iterdir()) == before


async def test_search_tool_returns_ranked_hits(mcp_client, vault_dir):
    """weft_search returns vault-relative paths, snippets and scores over MCP."""
    (vault_dir / "notes" / "crdt.md").write_text("CRDTs merge.\nCRDT again.\n")
    async with mcp_client:
        result = await mcp_client.call_tool("weft_search", {"query": "crdt"})
    assert result.is_error is False
    assert result.structured_content == {
        "result": [
            {"path": "notes/crdt.md", "snippet": "CRDTs merge.\nCRDT again.", "score": 2}
        ]
    }


@pytest.mark.parametrize(
    "args",
    [{"query": ""}, {"query": "a", "limit": 0}, {"query": "a", "limit": 51}, {}],
)
async def test_search_tool_rejects_invalid_input(mcp_client, args):
    """Schema constraints reject bad input before the search function runs."""
    async with mcp_client:
        result = await mcp_client.call_tool("weft_search", args)
    assert result.is_error is True
