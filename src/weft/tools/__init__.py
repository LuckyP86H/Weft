"""MCP tool adapters.

Each module exposes ``register(mcp, vault)``; ``capture`` also takes the
folder it files into. A tool here is a thin shell: it declares the schema the
agent sees and delegates to plain Python elsewhere. Domain logic never lives
in this package, and never imports ``mcp`` outside it.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from weft.capture import INBOX_DIR
from weft.tools import capture, scrub, search, suggest_links, vault_info
from weft.vault import Vault


def register_all(mcp: MCPServer, vault: Vault, *, inbox_dir: str = INBOX_DIR) -> None:
    """Register every Weft tool on ``mcp``."""
    vault_info.register(mcp, vault)
    scrub.register(mcp, vault)
    search.register(mcp, vault)
    suggest_links.register(mcp, vault)
    capture.register(mcp, vault, inbox_dir)
