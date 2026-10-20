"""``weft_suggest_links``: which existing notes should this one link to?

Why a tool, not a resource: the agent asks about a specific note or draft at
a moment of its choosing and gets a ranking back, an action with a result.
Why it only suggests: deciding which links are real connections is judgment,
so the agent (and you) pick from the ranking; the server never edits a note.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from weft.links import DEFAULT_LIMIT, suggest_links
from weft.vault import Vault, VaultError

MAX_LIMIT = 50


def register(mcp: MCPServer, vault: Vault) -> None:
    """Register the ``weft_suggest_links`` tool on ``mcp``."""

    @mcp.tool(name="weft_suggest_links")
    def weft_suggest_links(
        note_path: Annotated[
            str | None,
            Field(min_length=1, description="Vault-relative path of an existing note."),
        ] = None,
        text: Annotated[
            str | None, Field(min_length=1, description="Draft text not yet saved.")
        ] = None,
        limit: Annotated[
            int, Field(ge=1, le=MAX_LIMIT, description="Maximum number of candidates.")
        ] = DEFAULT_LIMIT,
    ) -> list[dict[str, Any]]:
        """Rank existing notes as [[wikilink]] candidates for a note or draft text.

        Give exactly one of note_path or text. Each candidate comes with a
        score (its shared words, each weighted by how rare it is in the vault,
        so boilerplate every note has counts for almost nothing) and the shared
        words, most telling first. Notes the input already links to are left
        out. Nothing is written; you decide which links to insert.
        """
        try:
            suggestions = suggest_links(vault, note_path=note_path, text=text, limit=limit)
        except (ValueError, VaultError) as exc:
            # A ToolError carries its message to the agent so it can fix the
            # call; any other exception is reported only as "Error executing tool".
            raise ToolError(str(exc)) from exc
        return [asdict(s) for s in suggestions]
