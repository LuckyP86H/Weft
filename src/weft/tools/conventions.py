"""``weft://conventions``: the vault's own rules for agents (its AGENTS.md).

Why a resource, not a tool: it *shows* something rather than doing
something. It is fixed context the agent (or the user, in clients where
resources are attached by hand) reads before acting, so that a note Weft
files follows the same frontmatter, folders and hubs as the rest of the
vault. Weft does not interpret the rules; choosing a domain or hub from them
is judgment, so it stays with the agent.

The text is scrubbed on the way out, like search snippets: it is handed to
the agent and on to its model provider.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from weft.scrub import scrub
from weft.vault import CONVENTIONS_FILE, Vault

CONVENTIONS_URI = "weft://conventions"


def register(mcp: MCPServer, vault: Vault) -> None:
    """Register the conventions resource on ``mcp`` if the vault has an AGENTS.md."""
    path = vault.conventions_path
    if path is None:
        return

    @mcp.resource(
        CONVENTIONS_URI,
        name="vault_conventions",
        title=f"Vault conventions ({CONVENTIONS_FILE})",
        description=(
            "The vault's rules for agents: note anatomy, frontmatter fields, "
            "folders and hubs. Read before capturing."
        ),
        mime_type="text/markdown",
    )
    def vault_conventions() -> str:
        # Read fresh on every request, so edits show up without a restart.
        return scrub(path.read_text(encoding="utf-8", errors="replace")).scrubbed_text
