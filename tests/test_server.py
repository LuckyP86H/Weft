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


async def test_lists_vault_info_tool(mcp_client):
    """The server exposes exactly the v0.1 tools registered so far."""
    async with mcp_client:
        tools = await mcp_client.list_tools()
    assert sorted(t.name for t in tools.tools) == ["weft_capture", "weft_scrub", "weft_vault_info"]


async def test_vault_info_reports_the_injected_vault(mcp_client, vault_dir):
    """weft_vault_info reports the vault the server was built with."""
    async with mcp_client:
        result = await mcp_client.call_tool("weft_vault_info", {})
    assert result.structured_content == {
        "root": str(vault_dir.resolve()),
        "is_obsidian_vault": True,
        "note_count": 3,
    }


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


async def test_capture_tool_rejects_unknown_source_type(mcp_client):
    """An unknown source_type is rejected before any file is written."""
    async with mcp_client:
        result = await mcp_client.call_tool(
            "weft_capture", {"text": "x", "source_type": "gossip"}
        )
    assert result.is_error
