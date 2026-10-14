"""``weft_capture``: scrub text and file it as a note in the vault inbox.

Why a tool, not a resource or prompt: it writes a file, an action with side
effects. The agent supplies ``source_type`` and ``title_hint`` from its
understanding of the user's message; the server files deterministically.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from mcp.server.mcpserver import MCPServer

from weft.capture import capture
from weft.types import SourceType
from weft.vault import Vault


def register(mcp: MCPServer, vault: Vault) -> None:
    """Register the ``weft_capture`` tool on ``mcp``."""

    @mcp.tool(name="weft_capture")
    def weft_capture(
        text: str,
        source_type: SourceType,
        source: str | None = None,
        title_hint: str | None = None,
    ) -> dict[str, Any]:
        """Scrub ``text`` and file it as a new note in the vault's inbox.

        Secrets, emails and phone numbers are redacted before anything is
        written, including from the filename, title and source. An existing
        note is never overwritten. Returns the vault-relative note path and a
        counts-only redaction report.
        """
        result = capture(
            vault,
            text,
            source_type,
            now=datetime.now().astimezone(),
            source=source,
            title_hint=title_hint,
        )
        return {
            "note_path": result.note_path,
            "redactions": [asdict(r) for r in result.redactions],
        }
