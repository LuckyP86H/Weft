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
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from weft.capture import capture
from weft.types import SourceType
from weft.vault import Vault


def _summarize(note_path: str, redactions: list[dict[str, Any]], dry_run: bool) -> str:
    """One human-readable line: where the note went and what was redacted."""
    prefix = "[dry run] would capture to" if dry_run else "Captured to"
    summary = f"{prefix} {note_path}"
    if redactions:
        bits = ", ".join(f"{r['category']} x {r['count']}" for r in redactions)
        summary += f" (redacted: {bits})"
    return summary


def register(mcp: MCPServer, vault: Vault) -> None:
    """Register the ``weft_capture`` tool on ``mcp``."""

    @mcp.tool(
        name="weft_capture",
        annotations=ToolAnnotations(
            readOnlyHint=False,  # writes a file into the vault inbox
            destructiveHint=False,  # never overwrites or deletes
            idempotentHint=False,  # every call files a new note
        ),
    )
    def weft_capture(
        text: str,
        source_type: SourceType,
        source: str | None = None,
        title_hint: str | None = None,
        dry_run: bool = False,
    ) -> CallToolResult:
        """Scrub ``text`` and file it as a new note in the vault's inbox.

        Secrets, emails and phone numbers are redacted before anything is
        written, including from the filename, title and source. An existing
        note is never overwritten. Returns the vault-relative note path and a
        counts-only redaction report.

        Set ``dry_run`` to preview the filename and redaction report without
        writing anything.
        """
        try:
            result = capture(
                vault,
                text,
                source_type,
                now=datetime.now().astimezone(),
                source=source,
                title_hint=title_hint,
                dry_run=dry_run,
            )
        except ValueError as exc:
            # A ToolError carries its message to the agent; any other
            # exception is reported only as "Error executing tool".
            raise ToolError(str(exc)) from exc
        structured: dict[str, Any] = {
            "note_path": result.note_path,
            "redactions": [asdict(r) for r in result.redactions],
            "dry_run": dry_run,
        }
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=_summarize(result.note_path, structured["redactions"], dry_run),
                )
            ],
            structured_content=structured,
        )
