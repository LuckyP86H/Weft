"""``weft_search``: what did I write about X?

Why a tool, not a resource: the agent runs a query of its own choosing and
reasons over ranked results, an action with an answer, rather than the
client attaching a fixed document as context.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from weft.search import DEFAULT_LIMIT, search
from weft.vault import Vault

MAX_LIMIT = 50


def register(mcp: MCPServer, vault: Vault) -> None:
    """Register the ``weft_search`` tool on ``mcp``."""

    @mcp.tool(name="weft_search")
    def weft_search(
        query: Annotated[str, Field(min_length=1, description="Words to look for.")],
        limit: Annotated[
            int, Field(ge=1, le=MAX_LIMIT, description="Maximum number of results.")
        ] = DEFAULT_LIMIT,
    ) -> list[dict[str, Any]]:
        """Search the vault's markdown notes for any of the query's words.

        Case-insensitive. Results are ranked by how often the words appear
        (highest first), each with its vault-relative path, a short snippet
        around the first match, and its score.
        """
        return [asdict(hit) for hit in search(vault, query, limit)]
