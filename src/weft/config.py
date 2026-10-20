"""Where is the vault? Resolve it at startup, never hard-code it.

Weft has no built-in vault location, so moving to a new machine means
re-pointing one setting, not editing code. The path is looked up in this order
(first hit wins):

1. ``--vault`` CLI flag
2. ``WEFT_VAULT`` environment variable
3. the user config file (``weft config set-vault <path>`` writes it)

If none is set, resolution fails with instructions. It never guesses.

The same file can also name the folder captures go to (``inbox_dir``, set by
``weft config set-inbox``), relative to the vault so it moves with it.

This module only answers "where". It knows nothing about MCP or what is
inside the vault. Every input (env, config path) is passed in, so tests need no
patching of globals.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePath

ENV_VAULT = "WEFT_VAULT"
ENV_CONFIG = "WEFT_CONFIG"


class ConfigError(Exception):
    """Raised when the vault location is missing or unusable."""


@dataclass(frozen=True)
class ResolvedVault:
    """A vault directory plus a human-readable note of where it came from."""

    path: Path
    source: str  # human-readable origin, e.g. "--vault flag"


def user_config_path(env: Mapping[str, str] | None = None) -> Path:
    """Per-user config file. ``WEFT_CONFIG`` overrides the location."""
    env = os.environ if env is None else env
    if override := env.get(ENV_CONFIG):
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(env.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "weft" / "config.json"


def read_user_config(config_path: Path) -> dict:
    """Return the config file's contents, or ``{}`` if it does not exist."""
    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{config_path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{config_path} must contain a JSON object")
    return data


def save_vault_path(config_path: Path, vault: Path) -> Path:
    """Validate ``vault`` and persist it in the user config. Returns the path stored."""
    vault = _validate_dir(vault, source="the path you gave")
    _save_key(config_path, "vault_path", str(vault))
    return vault


def read_inbox_dir(config_path: Path) -> str | None:
    """The saved capture folder (vault-relative, POSIX), or ``None`` if unset."""
    stored = read_user_config(config_path).get("inbox_dir")
    if stored is None:
        return None
    return _validate_inbox_dir(str(stored), f"config file {config_path}")


def save_inbox_dir(config_path: Path, inbox_dir: str) -> str:
    """Validate ``inbox_dir`` and persist it in the user config. Returns the value stored.

    Only the shape is checked here (relative, no ``..``); the vault boundary
    still guards every write, and the folder is created on first capture.
    """
    inbox_dir = _validate_inbox_dir(inbox_dir, "the folder you gave")
    _save_key(config_path, "inbox_dir", inbox_dir)
    return inbox_dir


def _save_key(config_path: Path, key: str, value: str) -> None:
    """Set one key in the user config, keeping the others."""
    data = read_user_config(config_path)
    data[key] = value
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def resolve_vault(
    cli_vault: str | None,
    env: Mapping[str, str],
    config_path: Path,
) -> ResolvedVault:
    """Find the vault directory using the precedence documented above."""
    if cli_vault:
        return ResolvedVault(_validate_dir(Path(cli_vault), "--vault flag"), "--vault flag")
    if env_vault := env.get(ENV_VAULT):
        source = f"{ENV_VAULT} environment variable"
        return ResolvedVault(_validate_dir(Path(env_vault), source), source)
    if stored := read_user_config(config_path).get("vault_path"):
        source = f"config file {config_path}"
        return ResolvedVault(_validate_dir(Path(str(stored)), source), source)
    raise ConfigError(
        "No vault configured. Point Weft at your Obsidian vault with one of:\n"
        "  weft config set-vault /path/to/vault     (saved for this user)\n"
        f"  {ENV_VAULT}=/path/to/vault                 (environment variable)\n"
        "  weft serve --vault /path/to/vault        (per launch)\n"
        "Not sure where it is? Run: weft config detect"
    )


def _validate_inbox_dir(value: str, source: str) -> str:
    path = PurePath(value.strip())
    if not path.parts or path.is_absolute() or ".." in path.parts:
        raise ConfigError(
            f"Inbox folder from {source} must be a folder inside the vault, "
            f"like \"Inbox & Thoughts\": {value!r}"
        )
    return path.as_posix()


def _validate_dir(path: Path, source: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise ConfigError(f"Vault from {source} is not a directory: {resolved}")
    return resolved
