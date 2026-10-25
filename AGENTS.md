# AGENTS.md: working on the Weft code

This file is for coding agents (Claude Code and others) changing this repository. It isn't the vault `AGENTS.md` that Weft serves as `weft://conventions`; that one lives in the user's Obsidian vault.

Read [WEFT.md](WEFT.md) for the spec. §1 (agent vs. server), §2 (principles) and §9 (milestones and phases) matter most.

## Commands

Python 3.14 (from `.python-version`) and uv 0.13+.

```sh
uv sync                                  # install, using uv.lock
uv run pytest                            # all tests
uv run pylint $(git ls-files '*.py')     # lint, same as CI
uv run weft serve --vault /path/to/vault # run the server over stdio
```

CI (`.github/workflows/pylint.yml`, check name `build (3.14)`) runs `uv sync --locked`, then pytest, then pylint. Both must pass. If you add a dependency, update `uv.lock` with uv and commit it.

## Rules

1. **Judgment belongs to the agent, deterministic work to the server.** No model calls, no network calls and no fuzzy logic in Weft.
2. **Every write goes through the scrubber.** No tool may write unscrubbed text to the vault. Note text that a tool returns (snippets, matched terms, the conventions file) is scrubbed too. File names aren't scrubbed yet; phase 4's read boundary fixes that.
3. **Weft never edits, moves, renames or deletes an existing note.** `weft_capture` creates new files only, in exclusive mode (`Vault.create_unique`). Changing that is a product decision, not a refactor.
4. **Layering is one-way:** `cli → server → tools → (vault, domain)`. Only `server.py` and `tools/` import `mcp`. Domain modules (`scrub`, `capture`, `search`, `links`) are plain Python and don't import `mcp`.
5. **Tools are thin.** A module in `tools/` declares the schema the agent sees and delegates. A new tool also updates the tool-list assertion in `tests/test_server.py`.
6. **The redaction report holds counts only**, never the matched text.
7. **Settings live in the user config (`~/.config/weft/config.json`), never inside the vault.** That covers the vault path, `inbox_dir` and, later, `redact_terms`: a list of sensitive terms stored in a synced vault would leak the very terms it hides.
8. **Tests come with the change.** Use table-driven tests for scrubbing and ranking. `tests/test_cli_stdio.py` runs the real server over stdio, so keep it passing.

## Pull requests

- One small PR per change, from `main`. Paul reviews on GitHub, and teammates may review and merge.
- Under each review comment you addressed, reply "updated". If you didn't change anything, explain why.
- Update README.md and WEFT.md in the same PR when behavior changes. Describe only what the code does today.
