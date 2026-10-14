"""The vault as a safe filesystem boundary.

Every later feature (capture, search, link suggestions) touches the disk
through ``Vault``, which is what keeps the server inside the vault. It knows
nothing about MCP, scrubbing or note formats.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Obsidian's own bookkeeping and common tool folders: never user notes.
_SKIPPED_DIRS = {".obsidian", ".trash", ".git"}


class VaultError(Exception):
    """Base class for vault problems."""


class PathEscapeError(VaultError):
    """A requested path resolves outside the vault."""


@dataclass(frozen=True)
class VaultInfo:
    """A snapshot of the vault: where it is and what it holds."""

    root: str
    is_obsidian_vault: bool
    note_count: int


class Vault:
    """A directory treated as the boundary: nothing escapes it."""

    def __init__(self, root: Path) -> None:
        root = root.expanduser().resolve()
        if not root.is_dir():
            raise VaultError(f"Vault is not a directory: {root}")
        self.root = root

    def resolve(self, relative: str | Path) -> Path:
        """Map a vault-relative path to an absolute one, refusing escapes.

        Handles ``..`` segments, absolute paths and symlinks pointing outside.
        """
        candidate = (self.root / relative).resolve()
        if not candidate.is_relative_to(self.root):
            raise PathEscapeError(f"Path escapes the vault: {relative}")
        return candidate

    def iter_notes(self) -> Iterator[Path]:
        """Yield every markdown note, skipping Obsidian/tool folders and hidden dirs."""
        for path in sorted(self.root.rglob("*.md")):
            parts = path.relative_to(self.root).parts[:-1]
            if any(p in _SKIPPED_DIRS or p.startswith(".") for p in parts):
                continue
            if path.is_file():
                yield path

    @property
    def is_obsidian_vault(self) -> bool:
        """True when the directory looks like an Obsidian vault."""
        return (self.root / ".obsidian").is_dir()

    def info(self) -> VaultInfo:
        """Summarize the vault: path, Obsidian check, and note count."""
        return VaultInfo(
            root=str(self.root),
            is_obsidian_vault=self.is_obsidian_vault,
            note_count=sum(1 for _ in self.iter_notes()),
        )
