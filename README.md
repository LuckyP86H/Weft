# Weft

Privacy-first MCP server that weaves daily media, spontaneous thoughts, and project workflows into your local Obsidian graph. It extracts abstract technical patterns and metadata while stripping sensitive data like tokens or client names, seamlessly updating your vault with cross-linked, long-term knowledge.

The full spec and roadmap live in [WEFT.md](WEFT.md). This repo is currently the **foundation**: config, vault boundary, server wiring and CLI, with one proof-of-wiring tool (`weft_vault_info`). The scrub/capture/search/link tools build on it.

## Setup

```sh
uv sync
uv run weft config detect                  # vaults Obsidian knows about on this machine
uv run weft config set-vault "/path/to/vault"
uv run weft config show
```

### Where is my vault?

Weft has no built-in vault path. At startup it takes the first of:

1. `weft serve --vault <path>`
2. `WEFT_VAULT=<path>`
3. the saved setting from `weft config set-vault` (`~/.config/weft/config.json`)

If none is set it refuses to start and tells you how to fix it. On a new laptop, just run `weft config detect` and `set-vault` again.

### Use it from Claude Code

```sh
claude mcp add --transport stdio --scope user weft -- uv run --directory /path/to/Weft weft serve
```

Add `-e WEFT_VAULT=/path/to/vault` to pin the vault in the client config instead of the saved setting.

## Develop

```sh
uv run pytest
```

Layers, one-way dependencies (`cli → server → tools → vault`): `config`/`discovery` answer *where*, `vault` is the safe filesystem boundary, `tools/` are thin MCP adapters, `server.py` is the composition root. Only `server.py` and `tools/` import `mcp`.
