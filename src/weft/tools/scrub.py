"""``weft_scrub``: redact sensitive text and report counts by category.

Why a tool, not a resource: the agent calls it on text it is about to store,
an action with a result, rather than the client attaching it as context.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mcp.server.mcpserver import MCPServer

from weft.scrub import scrub
from weft.vault import Vault


def register(mcp: MCPServer, vault: Vault) -> None:  # pylint: disable=unused-argument
    """Register the ``weft_scrub`` tool on ``mcp``.

    ``vault`` is accepted for a uniform ``register`` signature; scrubbing is
    pure and reads no files.
    """

    @mcp.tool(name="weft_scrub")
    def weft_scrub(text: str) -> dict[str, Any]:
        """Redact secrets, email addresses and phone numbers from ``text``.

        Returns the scrubbed text (with visible [REDACTED:...] markers) and a
        report of how many of each category were removed. The report never
        contains the removed text itself.
        """
        result = scrub(text)
        return {
            "scrubbed_text": result.scrubbed_text,
            "redactions": [asdict(r) for r in result.redactions],
        }
