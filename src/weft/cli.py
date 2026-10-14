"""Command line entry point: ``weft serve`` and ``weft config ...``.

The only layer that reads the real environment, prints to a terminal, or
exits the process. Everything below it takes plain arguments.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from weft.config import (
    ConfigError,
    resolve_vault,
    save_vault_path,
    user_config_path,
)
from weft.discovery import detect_vaults, obsidian_registry_path
from weft.server import build_server
from weft.vault import Vault


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weft", description="Weft: Obsidian MCP server")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the MCP server over stdio")
    serve.add_argument("--vault", help="vault directory (overrides env and config file)")

    config = sub.add_parser("config", help="inspect or change Weft's settings")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_sub.add_parser("show", help="print the resolved vault and where it came from")
    config_sub.add_parser("detect", help="list vaults Obsidian knows about on this machine")
    set_vault = config_sub.add_parser("set-vault", help="save the vault path for this user")
    set_vault.add_argument("path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI. Returns the process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "serve":
            return _serve(args.vault)
        return _config(args)
    except ConfigError as exc:
        print(f"weft: {exc}", file=sys.stderr)
        return 1


def _serve(cli_vault: str | None) -> int:
    resolved = resolve_vault(cli_vault, os.environ, user_config_path())
    print(f"weft: serving vault {resolved.path} (from {resolved.source})", file=sys.stderr)
    build_server(Vault(resolved.path)).run("stdio")
    return 0


def _config(args: argparse.Namespace) -> int:
    if args.config_command == "set-vault":
        stored = save_vault_path(user_config_path(), Path(args.path))
        print(f"Saved vault: {stored}")
    elif args.config_command == "show":
        resolved = resolve_vault(None, os.environ, user_config_path())
        print(f"{resolved.path}\n  from {resolved.source}")
    elif args.config_command == "detect":
        vaults = detect_vaults(obsidian_registry_path())
        if not vaults:
            print("No Obsidian vaults found. Use: weft config set-vault /path/to/vault")
        for vault in vaults:
            print(vault)
    return 0
