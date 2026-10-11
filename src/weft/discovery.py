"""Find vaults Obsidian already knows about, so setup is a pick, not a typing exercise.

Obsidian keeps a registry of every vault you have opened in ``obsidian.json``
under its per-user app-data folder. On a new laptop that file points at the
*new* location, which is exactly why Weft never stores a vault path in code.

Read-only and best-effort: a missing or odd registry yields an empty list.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path


def obsidian_registry_path(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    if sys.platform == "win32":
        return Path(env.get("APPDATA") or home / "AppData" / "Roaming") / "obsidian" / "obsidian.json"
    return Path(env.get("XDG_CONFIG_HOME") or home / ".config") / "obsidian" / "obsidian.json"


def detect_vaults(registry_path: Path) -> list[Path]:
    """Vault directories listed in Obsidian's registry that exist on disk."""
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        entries = data["vaults"].values()
        paths = [Path(entry["path"]) for entry in entries]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []
    return sorted(p for p in paths if p.is_dir())
