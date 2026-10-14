"""Composition root: the one place that wires the layers together.

    config  -> says where the vault is        (cli.py calls it)
    vault   -> safe access to that directory
    tools   -> thin MCP adapters over vault/domain code
    server  -> this file: builds the MCPServer and hands it a Vault

The vault is passed in explicitly rather than read from a global, so tests can
build a server over a temp directory and nothing depends on import order.

stdio rule: stdout carries the JSON-RPC stream. Never ``print()`` in the
server; log to stderr.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from weft import __version__
from weft.tools import register_all
from weft.vault import Vault


def build_server(vault: Vault) -> MCPServer:
    """Assemble the Weft MCP server, bound to ``vault``."""
    mcp = MCPServer(
        name="weft",
        version=__version__,
        instructions=(
            "Weft files and finds notes in the user's local Obsidian vault. "
            "It runs deterministic operations only; judgment stays with you."
        ),
    )
    register_all(mcp, vault)
    return mcp
