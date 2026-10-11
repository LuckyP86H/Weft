"""The MCP layer, exercised through a real MCP client (in memory, no subprocess)."""

import pytest
from mcp import Client

from weft.server import build_server
from weft.vault import Vault


@pytest.fixture
def client(vault_dir):
    return Client(build_server(Vault(vault_dir)))


async def test_lists_vault_info_tool(client):
    async with client:
        tools = await client.list_tools()
    assert [t.name for t in tools.tools] == ["weft_vault_info"]


async def test_vault_info_reports_the_injected_vault(client, vault_dir):
    async with client:
        result = await client.call_tool("weft_vault_info", {})
    assert result.structured_content == {
        "root": str(vault_dir.resolve()),
        "is_obsidian_vault": True,
        "note_count": 3,
    }
