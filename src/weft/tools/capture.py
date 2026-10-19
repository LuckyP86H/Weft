"""``weft_capture``: scrub text and file it as a note in the vault inbox.

Why a tool, not a resource or prompt: it writes a file, an action with side
effects. The agent supplies ``source_type`` and ``title_hint`` from its
understanding of the user's message; the server files deterministically.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from weft.capture import INBOX_DIR, NoteMeta, capture
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


def register(mcp: MCPServer, vault: Vault, inbox_dir: str = INBOX_DIR) -> None:
    """Register the ``weft_capture`` tool on ``mcp``, filing into ``inbox_dir``."""

    @mcp.tool(
        name="weft_capture",
        annotations=ToolAnnotations(
            readOnlyHint=False,  # writes a file into the vault inbox
            destructiveHint=False,  # never overwrites or deletes
            idempotentHint=False,  # every call files a new note
        ),
    )
    # The parameters are the agent-facing schema, so they stay flat.
    def weft_capture(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        text: str,
        source_type: SourceType,
        source: str | None = None,
        title_hint: str | None = None,
        summary: Annotated[
            str | None, Field(description="One-sentence summary for the frontmatter.")
        ] = None,
        domain: Annotated[
            str | None, Field(description="Domain label, as the vault's conventions name it.")
        ] = None,
        hub: Annotated[
            str | None, Field(description="Name of an existing hub note to link as the parent.")
        ] = None,
        tags: Annotated[
            list[str] | None, Field(description="Obsidian tags, without spaces.")
        ] = None,
        dry_run: bool = False,
    ) -> CallToolResult:
        """Scrub ``text`` and file it as a new note in the vault's inbox.

        Secrets, emails and phone numbers are redacted before anything is
        written, including from the filename, title and source. An existing
        note is never overwritten. Returns the vault-relative note path and a
        counts-only redaction report.

        If the vault documents its conventions (for example an AGENTS.md at
        its root), fill ``summary``, ``domain``, ``hub`` and ``tags`` to match
        them, so the note fits in with the rest of the vault. ``hub`` must be
        an existing note. All four are optional and scrubbed too.

        Set ``dry_run`` to preview the filename and redaction report without
        writing anything.
        """
        try:
            result = capture(
                vault,
                text,
                source_type,
                now=datetime.now().astimezone(),
                inbox_dir=inbox_dir,
                source=source,
                title_hint=title_hint,
                meta=NoteMeta(summary=summary, domain=domain, hub=hub, tags=tuple(tags or ())),
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
