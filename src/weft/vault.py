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

    def _candidate_names(self, filename: str) -> Iterator[str]:
        """Yield ``filename``, then ``-2``, ``-3``, ... variants of its stem."""
        if Path(filename).name != filename:
            raise PathEscapeError(f"Filename must not contain a path: {filename}")
        stem, suffix = Path(filename).stem, Path(filename).suffix
        yield filename
        for attempt in range(2, 1000):
            yield f"{stem}-{attempt}{suffix}"

    def peek_unique(self, directory: str, filename: str) -> Path:
        """Return the path ``create_unique`` would use now, without creating it.

        A preview only: another writer may take the name before a real write.
        """
        target_dir = self.resolve(directory)
        for name in self._candidate_names(filename):
            if not (target_dir / name).exists():
                return target_dir / name
        raise VaultError(f"Could not find a free name for {filename}")

    def create_unique(self, directory: str, filename: str, content: str) -> Path:
        """Create ``filename`` in ``directory`` without ever overwriting a file.

        On a name collision, ``-2``, ``-3``, ... is appended to the stem.
        Creation uses exclusive mode, so two writers cannot pick the same name.
        """
        target_dir = self.resolve(directory)
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in self._candidate_names(filename):
            path = target_dir / name
            try:
                with path.open("x", encoding="utf-8") as handle:
                    handle.write(content)
            except FileExistsError:
                continue
            return path
        raise VaultError(f"Could not find a free name for {filename}")

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
