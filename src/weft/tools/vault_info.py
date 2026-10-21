"""``weft_vault_info``: which vault is the server bound to?

Why a tool, not a resource: the agent calls it to *check* something at a
moment of its choosing (an action with a result), rather than the client
attaching it as passive context.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mcp.server.mcpserver import MCPServer

from weft.vault import Vault


def register(mcp: MCPServer, vault: Vault) -> None:
    """Register the ``weft_vault_info`` tool on ``mcp``."""
    @mcp.tool(name="weft_vault_info")
    def weft_vault_info() -> dict[str, Any]:
        """Report the Obsidian vault Weft is connected to.

        Returns the vault's absolute path, whether it looks like an Obsidian
        vault (has a .obsidian folder), how many markdown notes it holds, and
        its conventions file (AGENTS.md) if it has one, readable as the
        weft://conventions resource.
        """
        return asdict(vault.info())
