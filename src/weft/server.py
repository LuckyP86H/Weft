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
from weft.capture import INBOX_DIR
from weft.tools import register_all
from weft.tools.conventions import CONVENTIONS_URI
from weft.vault import Vault


def instructions(vault: Vault) -> str:
    """What the agent is told about Weft when it connects."""
    text = (
        "Weft files and finds notes in the user's local Obsidian vault. "
        "It runs deterministic operations only; judgment stays with you."
    )
    if vault.conventions_path is not None:
        text += (
            f" This vault documents its conventions in its AGENTS.md, available as the "
            f"{CONVENTIONS_URI} resource. Read it before capturing, and fill "
            "weft_capture's note_type, domain, hub, summary and tags to match it."
        )
    return text


def build_server(vault: Vault, *, inbox_dir: str = INBOX_DIR) -> MCPServer:
    """Assemble the Weft MCP server, bound to ``vault``, capturing into ``inbox_dir``."""
    mcp = MCPServer(name="weft", version=__version__, instructions=instructions(vault))
    register_all(mcp, vault, inbox_dir=inbox_dir)
    return mcp
